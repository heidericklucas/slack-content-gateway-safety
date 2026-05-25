"""Tests for the OpenAI LLM classifier — fully mocked, no network."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

from app.classifier.llm import OpenAIClassifier
from app.schemas import Category
from tests.conftest import OpenAIResponseFactory


async def test_parses_well_formed_response(openai_response_factory: OpenAIResponseFactory) -> None:
    payload = json.dumps(
        {
            "scores": {
                "aggression": 0.62,
                "threat": 0.91,
                "harassment": 0.20,
            },
            "triggered": ["threat", "aggression"],
        }
    )
    client = AsyncMock()
    client.chat.completions.create.return_value = openai_response_factory.make(payload)
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("you'll regret this", context=[])

    assert verdict.max_score(Category.THREAT) == 0.91
    assert verdict.max_score(Category.AGGRESSION) == 0.62
    assert verdict.max_score(Category.HARASSMENT) == 0.20


async def test_strips_markdown_fences(openai_response_factory: OpenAIResponseFactory) -> None:
    payload = '```json\n{"scores": {"threat": 0.8}}\n```'
    client = AsyncMock()
    client.chat.completions.create.return_value = openai_response_factory.make(payload)
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("text", context=[])

    assert verdict.max_score(Category.THREAT) == 0.8


async def test_invalid_json_returns_empty_verdict(
    openai_response_factory: OpenAIResponseFactory,
) -> None:
    client = AsyncMock()
    client.chat.completions.create.return_value = openai_response_factory.make("not json at all")
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("text", context=[])

    assert verdict.signals == []


async def test_unknown_category_is_ignored(
    openai_response_factory: OpenAIResponseFactory,
) -> None:
    payload = json.dumps({"scores": {"unknown_category": 0.9, "threat": 0.4}})
    client = AsyncMock()
    client.chat.completions.create.return_value = openai_response_factory.make(payload)
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("text", context=[])

    assert verdict.max_score(Category.THREAT) == 0.4
    assert len(verdict.signals) == 1


async def test_score_clamped_to_unit_range(
    openai_response_factory: OpenAIResponseFactory,
) -> None:
    payload = json.dumps({"scores": {"threat": 5.0, "aggression": -1.0}})
    client = AsyncMock()
    client.chat.completions.create.return_value = openai_response_factory.make(payload)
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("text", context=[])

    assert verdict.max_score(Category.THREAT) == 1.0
    assert verdict.max_score(Category.AGGRESSION) == 0.0


async def test_empty_text_skips_api_call() -> None:
    client = AsyncMock()
    classifier = OpenAIClassifier(client=client, max_retries=1)

    verdict = await classifier.classify("", context=[])

    assert verdict.signals == []
    client.chat.completions.create.assert_not_called()
