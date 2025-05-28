import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

from ai import intent_classifier


def test_live_classifier_fallback(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("INTENT_CLASSIFIER_LIVE", "1")
    res = intent_classifier.classify_intent({"intent_id": "1", "domain": "eth"})
    assert res == "eth"
