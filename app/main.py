"""FastAPI entrypoint.

* Validates configuration at startup (Pydantic settings).
* Boots the SBERT model in a background task so readiness can flip
  once the model is loaded — Kubernetes won't route traffic until then.
* Exposes ``/healthz`` (liveness) and ``/readyz`` (readiness) probes.
* Mounts ``slack_bolt`` at ``/slack/events`` for signature verification
  and the URL-verification challenge.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, Response, status
from openai import AsyncOpenAI
from slack_bolt.adapter.fastapi.async_handler import AsyncSlackRequestHandler
from slack_sdk.web.async_client import AsyncWebClient

from app import __version__
from app.classifier import (
    ClassifierPipeline,
    EmbeddingThreatClassifier,
    KeywordClassifier,
    OpenAIClassifier,
)
from app.config import Settings, get_settings
from app.logging_config import configure_logging, get_logger
from app.slack import build_bolt_app
from app.slack.handlers import MessageHandler

logger = get_logger(__name__)


def build_pipeline(
    settings: Settings, openai_client: AsyncOpenAI
) -> tuple[ClassifierPipeline, EmbeddingThreatClassifier | None]:
    """Assemble the default classifier pipeline.

    Returns the pipeline and a reference to the embedding classifier (if enabled)
    so we can warm it up at startup.
    """

    embedding_classifier: EmbeddingThreatClassifier | None = None
    classifiers: list = [KeywordClassifier()]
    if settings.embedding_enabled:
        embedding_classifier = EmbeddingThreatClassifier(
            model_name=settings.embedding_model,
            similarity_threshold=settings.thresholds.threat_similarity,
        )
        classifiers.append(embedding_classifier)
    classifiers.append(
        OpenAIClassifier(
            client=openai_client,
            model=settings.openai_model,
            timeout=settings.openai_timeout_seconds,
        )
    )
    return ClassifierPipeline(classifiers=classifiers), embedding_classifier


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory — used by tests and by the CLI entrypoint."""

    settings = settings or get_settings()
    configure_logging(settings)

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key.get_secret_value())
    slack_client = AsyncWebClient(token=settings.slack_bot_token.get_secret_value())

    pipeline, embedding_classifier = build_pipeline(settings, openai_client)
    message_handler = MessageHandler(
        pipeline=pipeline, slack_client=slack_client, settings=settings
    )
    bolt_app = build_bolt_app(settings, message_handler)
    bolt_handler = AsyncSlackRequestHandler(bolt_app)

    ready_event = asyncio.Event()
    # Models that don't need warmup are immediately ready.
    if embedding_classifier is None:
        ready_event.set()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        async def _warmup() -> None:
            try:
                if embedding_classifier is not None:
                    await embedding_classifier.warmup()
            finally:
                ready_event.set()

        warmup_task = asyncio.create_task(_warmup())
        try:
            yield
        finally:
            warmup_task.cancel()
            await openai_client.close()

    fastapi_app = FastAPI(
        title="Slack Content Gateway Safety",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    @fastapi_app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "slack-content-gateway-safety", "version": __version__}

    @fastapi_app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @fastapi_app.get("/readyz", tags=["health"])
    async def readyz() -> Response:
        if ready_event.is_set():
            return Response(content='{"status":"ready"}', media_type="application/json")
        return Response(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content="warming up")

    @fastapi_app.post("/slack/events", include_in_schema=False)
    async def slack_events(req: Request) -> Response:
        return await bolt_handler.handle(req)

    return fastapi_app


def main() -> None:
    """Console entrypoint — ``python -m app.main`` or the Docker ``CMD``."""

    settings = get_settings()
    uvicorn.run(
        "app.main:create_app",
        host=settings.host,
        port=settings.port,
        log_config=None,
        factory=True,
    )


if __name__ == "__main__":
    main()
