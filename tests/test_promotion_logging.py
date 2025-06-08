import json
from pathlib import Path

import importlib
from ai import promote as promote_mod
from ai.voting import record_vote


def test_promotion_logs_votes(monkeypatch, tmp_path: Path) -> None:
    log_file = tmp_path / "mutation_log.json"
    monkeypatch.setenv("MUTATION_LOG", str(log_file))
    monkeypatch.setenv("FOUNDER_TOKEN", "promote:9999999999")
    monkeypatch.setenv("AI_VOTES_DIR", str(tmp_path / "votes"))
    patch_hash = "abc"
    monkeypatch.setenv("PATCH_HASH", patch_hash)
    import ai.mutation_log as mlog
    importlib.reload(mlog)
    importlib.reload(promote_mod)
    record_vote("s1", patch_hash, "Codex_v1", True, "ok", "t1")
    record_vote("s1", patch_hash, "Codex_v2", True, "ok", "t2")
    record_vote("s1", patch_hash, "ClaudeSim", True, "ok", "t3")

    src = tmp_path / "staging" / "s1"
    dst = tmp_path / "active" / "s1"
    src.mkdir(parents=True)
    (src / "file.txt").write_text("x")

    assert promote_mod.promote_strategy(src, dst, approved=True, trace_id="t")
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["event"] == "promotion"
    assert entries[-1]["vote_summary"]["quorum"] is True
