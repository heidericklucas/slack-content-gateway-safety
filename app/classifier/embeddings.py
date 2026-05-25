"""Semantic-similarity classifier — flags implicit threats via SBERT embeddings.

The corpus of threat exemplars is small and curated; we encode it once at
construction time and reuse the cached tensor for every message.

The model is loaded lazily through an injected factory so tests can pass
a stub. Loading happens off the event loop via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.classifier.base import AsyncClassifier
from app.logging_config import get_logger
from app.schemas import Category, Signal, Verdict

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


logger = get_logger(__name__)

THREAT_EXEMPLARS: tuple[str, ...] = (
    "vou te demitir",
    "isso vai custar caro",
    "vai se arrepender",
    "vai ter consequências",
    "isso não vai ficar assim",
    "isso pode custar o emprego",
    "posso acabar com sua carreira",
    "isso vai te prejudicar",
    "vai pagar caro por isso",
    "tome cuidado com o que está fazendo",
    "sei onde você mora",
    "you'll regret this",
    "this will cost you",
    "i'll end your career",
    "i know where you live",
)


def _default_model_loader(model_name: str) -> SentenceTransformer:
    """Default loader — imports lazily so test environments don't need torch."""

    from sentence_transformers import SentenceTransformer

    model: SentenceTransformer = SentenceTransformer(model_name)
    return model


@dataclass(slots=True)
class EmbeddingThreatClassifier(AsyncClassifier):
    """SBERT cosine-similarity classifier specialised on threat detection."""

    model_name: str
    similarity_threshold: float = 0.72
    model_loader: Callable[[str], SentenceTransformer] = field(default=_default_model_loader)
    name: str = "embedding_threat"
    _model: SentenceTransformer | None = field(default=None, init=False, repr=False)
    _exemplar_embeddings: Any = field(default=None, init=False, repr=False)

    async def warmup(self) -> None:
        """Eagerly load the model. Call from app startup to avoid first-request stalls."""

        if self._model is not None:
            return
        logger.info("embedding_model_loading", model=self.model_name)
        model = await asyncio.to_thread(self.model_loader, self.model_name)
        self._exemplar_embeddings = await asyncio.to_thread(
            model.encode, list(THREAT_EXEMPLARS), convert_to_tensor=True
        )
        self._model = model
        logger.info("embedding_model_ready", model=self.model_name, exemplars=len(THREAT_EXEMPLARS))

    async def classify(self, text: str, context: list[str]) -> Verdict:
        verdict = Verdict()
        if not text:
            return verdict

        try:
            await self.warmup()
            assert self._model is not None
            score = await asyncio.to_thread(self._max_similarity, text)
        except Exception as exc:
            logger.warning("embedding_classifier_error", error=str(exc))
            return verdict

        if score >= self.similarity_threshold:
            verdict.add(
                Signal(
                    category=Category.THREAT,
                    score=score,
                    source=self.name,
                    reason=f"cosine_similarity={score:.3f}",
                )
            )
        return verdict

    def _max_similarity(self, text: str) -> float:
        from sentence_transformers import util

        assert self._model is not None
        embedding = self._model.encode(text, convert_to_tensor=True)
        cosine_scores = util.cos_sim(embedding, self._exemplar_embeddings)
        return float(cosine_scores.max())
