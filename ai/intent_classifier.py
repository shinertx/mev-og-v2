"""ML/LLM-based intent classifier with stub fallback."""

from __future__ import annotations

import os
from typing import Any, Dict, cast

from core.logger import StructuredLogger

LOG = StructuredLogger("intent_classifier")


def _live_classify(intent: Dict[str, Any]) -> str:
    """Use OpenAI to classify intent if configured."""
    try:
        import openai

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        openai.api_key = api_key
        prompt = (
            "Predict the optimal execution domain or venue for this intent: "
            f"{intent}"
        )
        resp = openai.ChatCompletion.create(  # type: ignore[attr-defined]
            model=os.getenv("INTENT_MODEL", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
        )
        pred = cast(str, resp.choices[0].message.content).strip()
        LOG.log(
            "classify",
            intent_id=intent.get("intent_id", ""),
            predicted=pred,
            confidence=1.0,
        )
        return pred
    except Exception as exc:  # pragma: no cover - network
        LOG.log(
            "classifier_fail",
            intent_id=intent.get("intent_id", ""),
            error=str(exc),
        )
        return cast(str, intent.get("domain", "unknown"))


def classify_intent(intent: Dict[str, Any]) -> str:
    """Classify intent into target domain/venue."""
    if os.getenv("INTENT_CLASSIFIER_LIVE") == "1":
        return _live_classify(intent)
    domain = cast(str, intent.get("domain", "unknown"))
    LOG.log(
        "classify",
        intent_id=intent.get("intent_id", ""),
        predicted=domain,
        confidence=0.0,
    )
    return domain
