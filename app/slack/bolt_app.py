"""Wire up :mod:`slack_bolt`'s async app and route message events to our handler.

slack_bolt takes care of:

* signing-secret verification on the request body bytes
* the URL-verification challenge handshake
* honouring Slack's ``X-Slack-Retry-Num`` retry header
* acking within 3 seconds — we ack immediately and process in a background task
"""

from __future__ import annotations

import asyncio
from typing import Any

from slack_bolt.async_app import AsyncApp

from app.config import Settings
from app.logging_config import get_logger
from app.slack.handlers import MessageHandler

logger = get_logger(__name__)


def build_bolt_app(settings: Settings, message_handler: MessageHandler) -> AsyncApp:
    """Construct an :class:`AsyncApp` wired to ``message_handler``."""

    bolt_app = AsyncApp(
        token=settings.slack_bot_token.get_secret_value(),
        signing_secret=settings.slack_signing_secret.get_secret_value(),
    )

    # Hold strong references to background tasks so they aren't GC'd mid-flight.
    background_tasks: set[asyncio.Task[None]] = set()

    @bolt_app.event("message")
    async def _on_message(event: dict[str, Any], ack: Any, body: dict[str, Any]) -> None:
        await ack()
        retry_num = int(body.get("X-Slack-Retry-Num") or 0)
        if retry_num > settings.max_retry_attempts:
            logger.info("slack_retry_dropped", retry_num=retry_num)
            return
        task = asyncio.create_task(_safe_handle(message_handler, event))
        background_tasks.add(task)
        task.add_done_callback(background_tasks.discard)

    return bolt_app


async def _safe_handle(handler: MessageHandler, event: dict[str, Any]) -> None:
    try:
        await handler.handle(event)
    except Exception as exc:
        logger.exception("message_handler_error", error=str(exc))
