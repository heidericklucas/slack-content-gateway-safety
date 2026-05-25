"""Unit tests for the keyword classifier and legal-justification guard."""

from __future__ import annotations

import pytest

from app.classifier.keyword import KeywordClassifier, contains_legal_justification
from app.schemas import Category


@pytest.mark.parametrize(
    "text",
    [
        "I plan to file a formal complaint with the attorney general.",
        "Estou exercendo meu direito à privacidade.",
        "I have not consented to this monitoring.",
    ],
)
def test_legal_justification_detected(text: str) -> None:
    assert contains_legal_justification(text)


@pytest.mark.parametrize(
    "text",
    [
        "Hello team, how is your day?",
        "I disagree with the proposal.",
        "",
    ],
)
def test_legal_justification_not_detected(text: str) -> None:
    assert not contains_legal_justification(text)


def test_legal_justification_word_boundary() -> None:
    # "consentimentos" should not match the keyword "consentimento" wholesale.
    # Our pattern uses \b boundaries, so the substring inside another word doesn't trigger.
    assert not contains_legal_justification("inconsentimento aleatório")


async def test_legal_justification_short_circuits_pipeline() -> None:
    classifier = KeywordClassifier()
    verdict = await classifier.classify(
        "I will file a complaint with the attorney general.", context=[]
    )
    assert verdict.skip_remaining is True


async def test_explicit_threat_flagged() -> None:
    classifier = KeywordClassifier()
    verdict = await classifier.classify("você está demitido amanhã", context=[])
    assert verdict.skip_remaining is False
    assert verdict.max_score(Category.THREAT) == 1.0


async def test_abusive_keyword_flagged() -> None:
    classifier = KeywordClassifier()
    verdict = await classifier.classify("Você é um idiota completo.", context=[])
    assert verdict.max_score(Category.ABUSIVE_LANGUAGE) == 1.0


async def test_benign_message_emits_no_signals() -> None:
    classifier = KeywordClassifier()
    verdict = await classifier.classify("Thanks for the update, looks good.", context=[])
    assert verdict.signals == []
    assert verdict.skip_remaining is False


async def test_empty_text_returns_empty_verdict() -> None:
    classifier = KeywordClassifier()
    verdict = await classifier.classify("", context=[])
    assert verdict.signals == []
    assert verdict.skip_remaining is False
