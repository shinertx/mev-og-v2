"""Broadcast fake or bait intents to mislead rival bots."""

from __future__ import annotations

from typing import Dict

from core.logger import StructuredLogger

LOG = StructuredLogger("intent_ghost")


def ghost_intent(api_url: str, fake_intent: Dict[str, object]) -> None:
    """Send a fake intent to confuse rivals."""
    try:
        import requests  # type: ignore

        resp = requests.post(f"{api_url.rstrip('/')}/intents", json=fake_intent, timeout=3)
        resp.raise_for_status()
        LOG.log(
            "ghost_intent",
            intent_id=str(fake_intent.get("intent_id")),
            status="sent",
        )
    except Exception as exc:  # pragma: no cover - network or runtime
        LOG.log("ghost_intent_fail", error=str(exc))
