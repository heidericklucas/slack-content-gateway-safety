"""Slack message event handler.

The handler is intentionally thin — it pulls context, runs the
classifier pipeline, picks a warning to post (if any), and writes
structured logs. All Slack and OpenAI I/O is delegated to the
injected clients so the handler is trivially testable.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
from slack_sdk.errors import SlackApiError
from slack_sdk.web.async_client import AsyncWebClient

from app.classifier.pipeline import ClassifierPipeline
from app.config import Settings
from app.logging_config import get_logger
from app.schemas import Category, Verdict
from app.slack.warnings import render_warning

logger = get_logger(__name__)


@dataclass(slots=True)
class MessageHandler:
    """Encapsulates the per-message moderation flow."""

    pipeline: ClassifierPipeline
    slack_client: AsyncWebClient
    settings: Settings

    async def handle(self, event: dict) -> None:
        """Entry point — invoked by the bolt event listener."""

        if not self._should_process(event):
            return

        user_id: str = event["user"]
        text: str = event.get("text") or ""
        channel: str = event["channel"]
        ts: str = event["ts"]

        # contextvars are task-local under asyncio, so clearing on exit is safe.
        structlog.contextvars.bind_contextvars(
            slack_user=user_id, slack_channel=channel, slack_ts=ts
        )
        try:
            context = await self._fetch_context(channel, ts)
            verdict = await self.pipeline.classify(text, context)
            await self._maybe_warn(verdict, user_id, channel)
        finally:
            structlog.contextvars.clear_contextvars()

    def _should_process(self, event: dict) -> bool:
        if event.get("type") != "message":
            return False
        # Ignore bot echoes, edits, deletes, joins/leaves, etc.
        if event.get("bot_id") or event.get("subtype"):
            return False
        return bool(event.get("user") and event.get("channel") and event.get("ts"))

    async def _fetch_context(self, channel: str, latest_ts: str) -> list[str]:
        try:
            response = await self.slack_client.conversations_history(
                channel=channel,
                latest=latest_ts,
                limit=self.settings.context_message_limit,
                inclusive=True,
            )
        except SlackApiError as exc:
            logger.info("slack_history_unavailable", error=exc.response.get("error", "unknown"))
            return []

        messages = list(reversed(response.get("messages", [])))
        return [
            f"{m.get('user', '')}: {m['text']}"
            for m in messages
            if "bot_id" not in m and m.get("text")
        ]

    async def _maybe_warn(self, verdict: Verdict, user_id: str, channel: str) -> None:
        if verdict.skip_remaining:
            logger.info("warning_suppressed_legal_justification")
            return

        thresholds = {
            Category.AGGRESSION: self.settings.thresholds.aggression,
            Category.HARASSMENT: self.settings.thresholds.harassment,
            Category.THREAT: self.settings.thresholds.threat,
            Category.COERCIVE_AUTHORITY: self.settings.thresholds.coercive_authority,
            Category.CONDESCENSION: self.settings.thresholds.condescension,
            # Keyword classifier always emits a 1.0 for ABUSIVE_LANGUAGE — any score wins.
            Category.ABUSIVE_LANGUAGE: 0.5,
        }
        category = verdict.winning_category(thresholds)
        if category is None:
            logger.info("no_warning", signals=[s.source for s in verdict.signals])
            return

        warning = render_warning(category, user_id)
        try:
            await self.slack_client.chat_postMessage(channel=channel, text=warning)
        except SlackApiError as exc:
            logger.warning("warning_post_failed", error=exc.response.get("error", "unknown"))
            return

        logger.info(
            "warning_posted",
            category=category.value,
            sources=[s.source for s in verdict.signals],
        )
