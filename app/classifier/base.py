"""Classifier protocol — every signal source implements this interface."""

from __future__ import annotations

from typing import Protocol

from app.schemas import Verdict


class AsyncClassifier(Protocol):
    """A classifier produces a :class:`Verdict` for a message."""

    name: str

    async def classify(self, text: str, context: list[str]) -> Verdict:
        """Return a verdict, optionally using prior conversation ``context``.

        Implementations should never raise — log internally and return an
        empty verdict so the pipeline can keep evaluating other signals.
        """
        ...
