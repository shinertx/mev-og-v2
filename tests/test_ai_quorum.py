import json
from pathlib import Path

from ai.promote import promote_strategy
from ai.voting import record_vote, quorum_met


def test_record_vote_and_quorum(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_VOTES_DIR", str(tmp_path / "telemetry" / "ai_votes"))
    timestamp = "2025-01-01T00-00-00"
    record_vote("s1", "abc", "Codex_v1", True, "ok", timestamp)
    record_vote("s1", "abc", "Codex_v2", True, "ok", timestamp + "1")
    record_vote("s1", "abc", "ClaudeSim", True, "ok", timestamp + "2")
    file = tmp_path / "telemetry" / "ai_votes" / f"ai_vote_{timestamp}.json"
    assert file.exists()
    data = json.loads(file.read_text())
    assert data["vote"] is True
    assert quorum_met("s1", "abc")


def test_quorum_fail(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("AI_VOTES_DIR", str(tmp_path / "telemetry" / "ai_votes"))
    record_vote("s1", "xyz", "Codex_v1", True, "ok", "t1")
    record_vote("s1", "xyz", "Codex_v2", False, "bad", "t2")
    record_vote("s1", "xyz", "ClaudeSim", True, "ok", "t3")
    assert not quorum_met("s1", "xyz")


def test_promote_strategy_quorum(monkeypatch, tmp_path: Path) -> None:
    """promote_strategy should respect quorum rules."""
    monkeypatch.chdir(tmp_path)
    votes = tmp_path / "telemetry" / "ai_votes"
    votes.mkdir(parents=True)
    monkeypatch.setenv("AI_VOTES_DIR", str(votes))
    monkeypatch.setenv("FOUNDER_TOKEN", "promote:9999999999")
    patch_hash = "abc"
    monkeypatch.setenv("PATCH_HASH", patch_hash)

    src = tmp_path / "staging" / "s1"
    dst = tmp_path / "active" / "s1"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("")

    def write_vote(agent: str, vote: bool, ts: str) -> None:
        (votes / f"ai_vote_{ts}.json").write_text(
            json.dumps({
                "strategy_id": "s1",
                "patch_hash": patch_hash,
                "agent": agent,
                "vote": vote,
                "reason": "ok",
                "timestamp": ts,
            })
        )

    write_vote("Codex_v1", True, "t1")
    write_vote("Codex_v2", False, "t2")
    write_vote("ClaudeSim", True, "t3")

    assert not promote_strategy(src, dst, approved=True)

    write_vote("InternalDRL", True, "t4")

    assert promote_strategy(src, dst, approved=True)

