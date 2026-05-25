"""Tests for the pipeline orchestrator."""

from __future__ import annotations

from dataclasses import dataclass

from app.classifier.pipeline import ClassifierPipeline
from app.schemas import Category, Signal, Verdict


@dataclass
class _FakeClassifier:
    name: str
    verdict: Verdict
    calls: int = 0

    async def classify(self, text: str, context: list[str]) -> Verdict:
        self.calls += 1
        return self.verdict


@dataclass
class _Boom:
    name: str = "boom"

    async def classify(self, text: str, context: list[str]) -> Verdict:
        raise RuntimeError("intentional explosion")


async def test_pipeline_aggregates_all_verdicts() -> None:
    first = _FakeClassifier(
        name="a",
        verdict=Verdict(signals=[Signal(Category.AGGRESSION, 0.6, "a")]),
    )
    second = _FakeClassifier(
        name="b",
        verdict=Verdict(signals=[Signal(Category.THREAT, 0.7, "b")]),
    )
    pipeline = ClassifierPipeline([first, second])

    result = await pipeline.classify("text")

    assert first.calls == 1
    assert second.calls == 1
    assert result.max_score(Category.AGGRESSION) == 0.6
    assert result.max_score(Category.THREAT) == 0.7


async def test_skip_remaining_short_circuits() -> None:
    early = _FakeClassifier(
        name="legal",
        verdict=Verdict(skip_remaining=True),
    )
    later = _FakeClassifier(
        name="llm",
        verdict=Verdict(signals=[Signal(Category.THREAT, 0.9, "llm")]),
    )
    pipeline = ClassifierPipeline([early, later])

    result = await pipeline.classify("text")

    assert early.calls == 1
    assert later.calls == 0
    assert result.skip_remaining is True
    assert result.max_score(Category.THREAT) == 0.0


async def test_exceptions_dont_break_the_pipeline() -> None:
    after = _FakeClassifier(
        name="after",
        verdict=Verdict(signals=[Signal(Category.HARASSMENT, 0.8, "after")]),
    )
    pipeline = ClassifierPipeline([_Boom(), after])

    result = await pipeline.classify("text")

    assert after.calls == 1
    assert result.max_score(Category.HARASSMENT) == 0.8
