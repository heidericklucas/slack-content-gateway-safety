"""GPT-4o-based toxicity classifier.

Calls the OpenAI Chat Completions API with a tight JSON schema, retries
transient failures with exponential backoff, and converts the parsed
scores into :class:`~app.schemas.Signal` objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from openai import APIError, APITimeoutError, AsyncOpenAI, RateLimitError
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from app.classifier.base import AsyncClassifier
from app.logging_config import get_logger
from app.schemas import Category, Signal, Verdict

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a toxicity classifier for workplace chat messages. "
    "Given the conversation context below, respond ONLY with a JSON object "
    "matching exactly this schema: "
    '{"scores": {"<category>": <float 0..1>, ...}, "triggered": ["<category>", ...]}. '
    "Categories: aggression, harassment, threat, coercive_authority, condescension. "
    "`coercive_authority` covers subtle or indirect language that pressures, monitors, or "
    "corrects someone's behaviour by implying hierarchical control, surveillance, or piled-on "
    "questions that make the recipient feel micromanaged or distrusted. Do not flag a manager "
    "responding proportionately to prior unprofessional behaviour. "
    "Return only the JSON object — no prose, no markdown fences."
)

_OPENAI_CATEGORY_MAP: dict[str, Category] = {
    "aggression": Category.AGGRESSION,
    "harassment": Category.HARASSMENT,
    "threat": Category.THREAT,
    "coercive_authority": Category.COERCIVE_AUTHORITY,
    "condescension": Category.CONDESCENSION,
}


@dataclass(slots=True)
class OpenAIClassifier(AsyncClassifier):
    """Async OpenAI classifier with retries."""

    client: AsyncOpenAI
    model: str = "gpt-4o"
    timeout: float = 15.0
    temperature: float = 0.2
    max_retries: int = 3
    name: str = "openai_llm"

    async def classify(self, text: str, context: list[str]) -> Verdict:
        verdict = Verdict()
        if not text:
            return verdict

        user_content = "\n".join(context) if context else text

        response = None
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_random_exponential(multiplier=0.5, max=8),
                retry=retry_if_exception_type((APITimeoutError, RateLimitError, APIError)),
                reraise=True,
            ):
                with attempt:
                    response = await self.client.chat.completions.create(
                        model=self.model,
                        messages=[
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_content},
                        ],
                        temperature=self.temperature,
                        timeout=self.timeout,
                        response_format={"type": "json_object"},
                    )
        except Exception as exc:
            logger.warning("openai_classifier_error", error=str(exc))
            return verdict

        if response is None:  # never executed in practice — tenacity reraises
            return verdict

        raw = (response.choices[0].message.content or "").strip()
        if not raw:
            return verdict

        # Belt-and-braces — some models still emit ```json fences despite response_format.
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw.removeprefix("json").strip()

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("openai_response_not_json", raw_prefix=raw[:80])
            return verdict

        scores = parsed.get("scores") or {}
        if not isinstance(scores, dict):
            return verdict

        for raw_category, raw_score in scores.items():
            category = _OPENAI_CATEGORY_MAP.get(str(raw_category).lower())
            if category is None:
                continue
            try:
                score = float(raw_score)
            except (TypeError, ValueError):
                continue
            score = max(0.0, min(1.0, score))
            verdict.add(Signal(category=category, score=score, source=self.name))

        return verdict
