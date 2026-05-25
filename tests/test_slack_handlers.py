"""Tests for the Slack message handler.

These exercise the full classification → warning flow with mocked Slack
and a stub pipeline, so we can verify routing decisions without any
network.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

from app.classifier.pipeline import ClassifierPipeline
from app.config import Settings
from app.schemas import Category, Signal, Verdict
from app.slack.handlers import MessageHandler


@dataclass
class _StaticClassifier:
    """A classifier that always returns the same prebuilt verdict."""

    name: str
    verdict: Verdict

    async def classify(self, text: str, context: list[str]) -> Verdict:
        return self.verdict


def _make_handler(settings: Settings, slack_client: AsyncMock, verdict: Verdict) -> MessageHandler:
    pipeline = ClassifierPipeline([_StaticClassifier(name="stub", verdict=verdict)])
    return MessageHandler(pipeline=pipeline, slack_client=slack_client, settings=settings)


def _message_event(**overrides: object) -> dict:
    return {
        "type": "message",
        "user": "U123",
        "text": "Hello world",
        "channel": "C42",
        "ts": "1234.5678",
        **overrides,
    }


async def test_bot_messages_are_ignored(settings: Settings, slack_client: AsyncMock) -> None:
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.THREAT, 0.9, "stub")])
    )
    await handler.handle(_message_event(bot_id="B1"))
    slack_client.chat_postMessage.assert_not_called()


async def test_subtype_events_are_ignored(settings: Settings, slack_client: AsyncMock) -> None:
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.THREAT, 0.9, "stub")])
    )
    await handler.handle(_message_event(subtype="message_changed"))
    slack_client.chat_postMessage.assert_not_called()


async def test_non_message_events_are_ignored(settings: Settings, slack_client: AsyncMock) -> None:
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.THREAT, 0.9, "stub")])
    )
    await handler.handle({"type": "channel_joined"})
    slack_client.chat_postMessage.assert_not_called()


async def test_threat_above_threshold_posts_warning(
    settings: Settings, slack_client: AsyncMock
) -> None:
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.THREAT, 0.9, "stub")])
    )
    await handler.handle(_message_event())
    slack_client.chat_postMessage.assert_awaited_once()
    args = slack_client.chat_postMessage.await_args
    assert args.kwargs["channel"] == "C42"
    assert "<@U123>" in args.kwargs["text"]
    assert args.kwargs["text"].startswith(":rotating_light:")


async def test_below_threshold_does_not_warn(settings: Settings, slack_client: AsyncMock) -> None:
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.AGGRESSION, 0.1, "stub")])
    )
    await handler.handle(_message_event())
    slack_client.chat_postMessage.assert_not_called()


async def test_skip_remaining_suppresses_warning(
    settings: Settings, slack_client: AsyncMock
) -> None:
    handler = _make_handler(
        settings,
        slack_client,
        Verdict(
            signals=[Signal(Category.THREAT, 0.9, "stub")],
            skip_remaining=True,
        ),
    )
    await handler.handle(_message_event())
    slack_client.chat_postMessage.assert_not_called()


async def test_threat_beats_aggression_in_priority(
    settings: Settings, slack_client: AsyncMock
) -> None:
    handler = _make_handler(
        settings,
        slack_client,
        Verdict(
            signals=[
                Signal(Category.AGGRESSION, 0.95, "stub"),
                Signal(Category.THREAT, 0.55, "stub"),
            ]
        ),
    )
    await handler.handle(_message_event())
    args = slack_client.chat_postMessage.await_args
    assert args.kwargs["text"].startswith(":rotating_light:")  # threat template


async def test_history_fetch_failure_is_non_fatal(
    settings: Settings, slack_client: AsyncMock
) -> None:
    from slack_sdk.errors import SlackApiError

    slack_client.conversations_history.side_effect = SlackApiError(
        message="ratelimited", response={"ok": False, "error": "ratelimited"}
    )
    handler = _make_handler(
        settings, slack_client, Verdict(signals=[Signal(Category.THREAT, 0.9, "stub")])
    )
    await handler.handle(_message_event())
    slack_client.chat_postMessage.assert_awaited_once()
