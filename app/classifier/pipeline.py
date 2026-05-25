"""Runs a sequence of classifiers, honouring early-exit semantics."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from app.classifier.base import AsyncClassifier
from app.logging_config import get_logger
from app.schemas import Verdict

logger = get_logger(__name__)


@dataclass(slots=True)
class ClassifierPipeline:
    """Compose classifiers; the first to set ``skip_remaining`` short-circuits."""

    classifiers: Sequence[AsyncClassifier]

    async def classify(self, text: str, context: list[str] | None = None) -> Verdict:
        ctx = context or []
        aggregate = Verdict()
        for classifier in self.classifiers:
            try:
                partial = await classifier.classify(text, ctx)
            except Exception as exc:
                logger.warning("classifier_failed", classifier=classifier.name, error=str(exc))
                continue
            aggregate.extend(partial)
            if aggregate.skip_remaining:
                logger.info("pipeline_skipped_remaining", at=classifier.name)
                break
        return aggregate
