"""Tests for strategy scoring and pruning utilities."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from ai.mutator import score_strategies, prune_strategies


def test_score_and_prune(tmp_path):
    metrics = {
        "stratA": {
            "pnl": 10,
            "returns": [1, 2, 3],
            "risk": 0.5,
            "volatility": 0.2,
            "wins": 3,
            "losses": 1,
            "latencies": [0.1, 0.2],
            "opportunities": 4,
        },
        "stratB": {
            "pnl": -5,
            "risk": 1.5,
            "volatility": 0.5,
            "wins": 0,
            "losses": 2,
            "latencies": [1.0],
            "opportunities": 1,
            "chaos_fail": True,
        },
    }
    scores = score_strategies(metrics, output_path=str(tmp_path / "scores.json"))
    assert scores[0]["strategy"] == "stratA"

    flagged = prune_strategies(metrics, audit_feedback={"stratB": True})
    assert "stratB" in flagged
    assert "stratA" not in flagged
