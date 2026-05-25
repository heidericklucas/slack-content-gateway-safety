"""Domain schemas for classification verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Category(StrEnum):
    """Toxicity categories the system reasons about.

    ``THREAT`` and ``ABUSIVE_LANGUAGE`` are surfaced as user-facing
    warnings; the rest contribute to scoring/aggregation.
    """

    AGGRESSION = "aggression"
    HARASSMENT = "harassment"
    THREAT = "threat"
    COERCIVE_AUTHORITY = "coercive_authority"
    CONDESCENSION = "condescension"
    ABUSIVE_LANGUAGE = "abusive_language"


# Priority order when multiple categories trigger — higher index wins.
CATEGORY_PRIORITY: tuple[Category, ...] = (
    Category.CONDESCENSION,
    Category.HARASSMENT,
    Category.AGGRESSION,
    Category.ABUSIVE_LANGUAGE,
    Category.COERCIVE_AUTHORITY,
    Category.THREAT,
)


@dataclass(frozen=True, slots=True)
class Signal:
    """One classifier's score for one category, with provenance."""

    category: Category
    score: float
    source: str
    reason: str = ""


@dataclass(slots=True)
class Verdict:
    """Aggregated classifier output for a single message."""

    signals: list[Signal] = field(default_factory=list)
    skip_remaining: bool = False  # set by upstream guards (e.g. legal justification)

    def add(self, signal: Signal) -> None:
        self.signals.append(signal)

    def extend(self, other: Verdict) -> None:
        self.signals.extend(other.signals)
        self.skip_remaining = self.skip_remaining or other.skip_remaining

    def max_score(self, category: Category) -> float:
        return max(
            (s.score for s in self.signals if s.category == category),
            default=0.0,
        )

    def triggered(self, thresholds: dict[Category, float]) -> set[Category]:
        """Return the set of categories whose max score crosses its threshold."""

        return {
            category
            for category, threshold in thresholds.items()
            if self.max_score(category) >= threshold
        }

    def winning_category(self, thresholds: dict[Category, float]) -> Category | None:
        """Pick the highest-priority triggered category, or ``None``."""

        triggered = self.triggered(thresholds)
        if not triggered:
            return None
        return max(triggered, key=CATEGORY_PRIORITY.index)
