"""Rule-based keyword classifiers.

Cheap, fast, and explainable signals that run before any model call.
They cover three needs:

* **Legal-justification short-circuit** — if a message asserts a legal
  right (privacy, labour law, formal complaints), we suppress further
  flagging so users invoking their rights aren't moderated.
* **Explicit threat keywords** — Portuguese/English phrases that map
  directly to dismissal threats and retaliation.
* **Abusive language keywords** — slurs and demeaning labels.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.classifier.base import AsyncClassifier
from app.schemas import Category, Signal, Verdict

# Phrases that mark a message as legitimate legal/labour speech.
# Match on word boundaries to avoid spurious hits inside other words.
LEGAL_JUSTIFICATION_PHRASES: tuple[str, ...] = (
    "attorney general",
    "massachusetts law",
    "direito trabalhista",
    "direitos trabalhistas",
    "direito à privacidade",
    "right to privacy",
    "fair labor division",
    "consentimento",
    "consentimento expresso",
    "formal complaint",
    "complaint with the attorney general",
    "complaint with attorney general",
    "complaint with fair labor division",
    "file a complaint",
    "file a formal complaint",
    "direito de recusar",
    "não consinto",
    "não dou consentimento",
    "i do not consent",
    "i have not consented",
    "i never signed",
    "i never agreed",
    "right to keep personal property free from monitoring",
    "direito de manter propriedade pessoal livre de monitoramento",
)

EXPLICIT_THREAT_PHRASES: tuple[str, ...] = (
    "vou te demitir",
    "você está demitido",
    "isso vai custar caro",
    "vai se arrepender",
    "te coloco na rua",
    "não vai mais trabalhar aqui",
    "you're fired",
    "i'll have you fired",
)

ABUSIVE_KEYWORDS: tuple[str, ...] = (
    # pt-BR
    "idiota",
    "burro",
    "imbecil",
    "estúpido",
    "palhaço",
    "otário",
    "babaca",
    "retardado",
    "ignorante",
    "nojento",
    "vergonha",
    "ridículo",
    # en
    "idiot",
    "moron",
    "stupid",
    "dumbass",
    "clown",
    "loser",
)


def _compile_phrase_pattern(phrases: Iterable[str]) -> re.Pattern[str]:
    """Compile an alternation of phrases anchored on word boundaries.

    Uses ``\\b`` boundaries so e.g. ``"idiot"`` doesn't match inside ``"idiotic"``.
    """

    alternation = "|".join(re.escape(phrase) for phrase in phrases)
    return re.compile(rf"\b(?:{alternation})\b", re.IGNORECASE)


_LEGAL_PATTERN = _compile_phrase_pattern(LEGAL_JUSTIFICATION_PHRASES)
_EXPLICIT_THREAT_PATTERN = _compile_phrase_pattern(EXPLICIT_THREAT_PHRASES)
_ABUSIVE_PATTERN = _compile_phrase_pattern(ABUSIVE_KEYWORDS)


def contains_legal_justification(text: str) -> bool:
    """Public helper — used by callers that want a quick guard check."""

    return bool(_LEGAL_PATTERN.search(text or ""))


@dataclass(slots=True)
class KeywordClassifier(AsyncClassifier):
    """Synchronous rule check, wrapped in an async interface for the pipeline."""

    name: str = "keyword"

    async def classify(self, text: str, context: list[str]) -> Verdict:
        verdict = Verdict()
        if not text:
            return verdict

        if contains_legal_justification(text):
            verdict.skip_remaining = True
            verdict.add(
                Signal(
                    category=Category.THREAT,  # unused, but we mark the source
                    score=0.0,
                    source=self.name,
                    reason="legal_justification_detected",
                )
            )
            return verdict

        if _EXPLICIT_THREAT_PATTERN.search(text):
            verdict.add(
                Signal(
                    category=Category.THREAT,
                    score=1.0,
                    source=self.name,
                    reason="explicit_threat_keyword",
                )
            )

        if _ABUSIVE_PATTERN.search(text):
            verdict.add(
                Signal(
                    category=Category.ABUSIVE_LANGUAGE,
                    score=1.0,
                    source=self.name,
                    reason="abusive_keyword",
                )
            )

        return verdict
