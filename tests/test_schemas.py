"""Unit tests for the verdict aggregation primitives."""

from __future__ import annotations

from app.schemas import CATEGORY_PRIORITY, Category, Signal, Verdict


def _signal(category: Category, score: float, source: str = "test") -> Signal:
    return Signal(category=category, score=score, source=source)


def test_max_score_returns_highest() -> None:
    verdict = Verdict(
        signals=[
            _signal(Category.AGGRESSION, 0.3),
            _signal(Category.AGGRESSION, 0.8),
            _signal(Category.HARASSMENT, 0.9),
        ]
    )
    assert verdict.max_score(Category.AGGRESSION) == 0.8
    assert verdict.max_score(Category.HARASSMENT) == 0.9
    assert verdict.max_score(Category.THREAT) == 0.0


def test_triggered_categories() -> None:
    verdict = Verdict(
        signals=[
            _signal(Category.AGGRESSION, 0.6),
            _signal(Category.HARASSMENT, 0.4),
            _signal(Category.THREAT, 0.55),
        ]
    )
    triggered = verdict.triggered(
        {Category.AGGRESSION: 0.5, Category.HARASSMENT: 0.5, Category.THREAT: 0.5}
    )
    assert triggered == {Category.AGGRESSION, Category.THREAT}


def test_winning_category_priority_threat_wins() -> None:
    verdict = Verdict(
        signals=[
            _signal(Category.AGGRESSION, 0.9),
            _signal(Category.THREAT, 0.6),
        ]
    )
    winner = verdict.winning_category({Category.AGGRESSION: 0.5, Category.THREAT: 0.5})
    assert winner is Category.THREAT


def test_winning_category_none_when_no_trigger() -> None:
    verdict = Verdict(
        signals=[
            _signal(Category.AGGRESSION, 0.1),
            _signal(Category.THREAT, 0.2),
        ]
    )
    assert verdict.winning_category({Category.AGGRESSION: 0.5, Category.THREAT: 0.5}) is None


def test_extend_combines_signals_and_skip_flag() -> None:
    a = Verdict(signals=[_signal(Category.AGGRESSION, 0.4)], skip_remaining=False)
    b = Verdict(signals=[_signal(Category.HARASSMENT, 0.6)], skip_remaining=True)
    a.extend(b)
    assert {s.category for s in a.signals} == {Category.AGGRESSION, Category.HARASSMENT}
    assert a.skip_remaining is True


def test_category_priority_covers_all_categories() -> None:
    # CATEGORY_PRIORITY must list every Category so winning_category never KeyErrors.
    assert set(CATEGORY_PRIORITY) == set(Category)
