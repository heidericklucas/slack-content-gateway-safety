"""Smoke tests for the FastAPI app — health probes only.

We avoid importing the SBERT model in tests by setting ``EMBEDDING_ENABLED=false``.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings, Thresholds
from app.main import create_app


@pytest.fixture
def app_settings() -> Settings:
    return Settings(
        slack_bot_token="xoxb-test",  # type: ignore[arg-type]
        slack_signing_secret="signing-secret",  # type: ignore[arg-type]
        openai_api_key="sk-test",  # type: ignore[arg-type]
        embedding_enabled=False,
        log_format="console",
        thresholds=Thresholds(),
    )


async def test_healthz(app_settings: Settings) -> None:
    app = create_app(settings=app_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_ready_without_embeddings(app_settings: Settings) -> None:
    app = create_app(settings=app_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # The lifespan runs only when entering the AsyncClient; readiness flips
        # immediately when embeddings are disabled.
        response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_root_metadata(app_settings: Settings) -> None:
    app = create_app(settings=app_settings)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "slack-content-gateway-safety"
    assert "version" in body
