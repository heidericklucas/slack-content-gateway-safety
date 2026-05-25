"""Application configuration loaded from environment variables.

Uses pydantic-settings so the app fails fast at startup if required
credentials are missing, instead of crashing on the first Slack event.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Thresholds(BaseSettings):
    """Per-category score thresholds used by the classifier pipeline.

    Overridable via ``THRESHOLD_*`` env vars (e.g. ``THRESHOLD_AGGRESSION=0.6``).
    """

    model_config = SettingsConfigDict(env_prefix="THRESHOLD_", extra="ignore")

    aggression: float = 0.5
    harassment: float = 0.5
    threat: float = 0.5
    coercive_authority: float = 0.5
    condescension: float = 0.3
    threat_similarity: float = 0.72


class Settings(BaseSettings):
    """Top-level application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Slack
    slack_bot_token: SecretStr = Field(..., description="xoxb-… Slack bot token")
    slack_signing_secret: SecretStr = Field(
        ..., description="Slack signing secret for HMAC verification"
    )

    # OpenAI
    openai_api_key: SecretStr = Field(..., description="OpenAI API key")
    openai_model: str = Field("gpt-4o", description="OpenAI model used for classification")
    openai_timeout_seconds: float = 15.0

    # Embedding model (sentence-transformers)
    embedding_model: str = Field(
        "sentence-transformers/paraphrase-MiniLM-L6-v2",
        description="HuggingFace model id for the embedding similarity classifier",
    )
    embedding_enabled: bool = True

    # Server
    port: int = 5000
    host: str = "0.0.0.0"  # noqa: S104 — container listens on all interfaces by design
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"

    # Slack event handling
    context_message_limit: int = 20
    # Honour Slack's `X-Slack-Retry-Num` header — set to 0 to ignore retries.
    max_retry_attempts: int = 2

    thresholds: Thresholds = Field(default_factory=Thresholds)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached :class:`Settings` instance.

    Cached so the (potentially expensive) env parsing only runs once per process.
    """

    return Settings()
