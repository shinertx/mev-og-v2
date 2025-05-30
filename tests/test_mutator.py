"""Tests for strategy scoring and pruning utilities."""



from ai.mutator import score_strategies, prune_strategies


def test_score_and_prune(tmp_path):
    metrics = {
        "stratA": {
            "realized_pnl": 10,
            "sharpe": 1.2,
            "drawdown": 0.1,
            "win_rate": 0.75,
            "failures": 0,
            "chaos_failures": 0,
            "dr_triggers": 0,
        },
        "stratB": {
            "realized_pnl": -5,
            "sharpe": -0.3,
            "drawdown": 0.5,
            "win_rate": 0.2,
            "failures": 2,
            "chaos_failures": 1,
            "dr_triggers": 1,
        },
    }
    scores = score_strategies(metrics, output_path=str(tmp_path / "scores.json"), top_n=1)
    assert scores[0]["strategy"] == "stratA"
    assert "version" in scores[0]

    flagged = prune_strategies(metrics, audit_feedback={"stratB": True})
    assert "stratB" in flagged
    assert "stratA" not in flagged
