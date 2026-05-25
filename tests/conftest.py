"""Shared pytest fixtures.

Tests run against a fully in-memory app: no network, no Slack, no OpenAI.
Fixtures expose:

* ``settings``      — a deterministic :class:`Settings` with dummy creds
* ``slack_client``  — :class:`AsyncMock` standing in for ``AsyncWebClient``
* ``openai_client`` — :class:`AsyncMock` standing in for ``AsyncOpenAI``
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest

from app.config import Settings, Thresholds


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear environment variables that could shadow test fixtures."""

    for var in [
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "LOG_LEVEL",
        "LOG_FORMAT",
    ]:
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture
def settings() -> Settings:
    return Settings(
        slack_bot_token="xoxb-test",  # type: ignore[arg-type]
        slack_signing_secret="signing-secret",  # type: ignore[arg-type]
        openai_api_key="sk-test",  # type: ignore[arg-type]
        openai_model="gpt-4o",
        embedding_enabled=False,
        log_format="console",
        log_level="INFO",
        thresholds=Thresholds(),
    )


@pytest.fixture
def slack_client() -> AsyncMock:
    mock = AsyncMock()
    mock.conversations_history.return_value = {"messages": []}
    mock.chat_postMessage.return_value = {"ok": True}
    return mock


@pytest.fixture
def openai_response_factory() -> OpenAIResponseFactory:
    return OpenAIResponseFactory()


class OpenAIResponseFactory:
    """Builds OpenAI-shaped chat.completions responses for tests."""

    @staticmethod
    def make(content: str) -> object:
        class _Message:
            def __init__(self, c: str) -> None:
                self.content = c

        class _Choice:
            def __init__(self, c: str) -> None:
                self.message = _Message(c)

        class _Response:
            def __init__(self, c: str) -> None:
                self.choices = [_Choice(c)]

        return _Response(content)
