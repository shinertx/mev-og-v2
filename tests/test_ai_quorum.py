import json
from pathlib import Path

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

