import os
import subprocess
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "batch_ops.py"


def run_script(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = env.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )


def test_batch_promote_pause(tmp_path: Path) -> None:
    staging = tmp_path / "staging" / "s1"
    active = tmp_path / "active" / "s1"
    paused = tmp_path / "paused"
    staging.mkdir(parents=True)
    (staging / "file.txt").write_text("x")
    env = os.environ.copy()
    env["FOUNDER_TOKEN"] = "promote:9999999999"
    env["PWD"] = str(tmp_path)
    env["AI_VOTES_DIR"] = str(tmp_path / "telemetry" / "ai_votes")
    env["PATCH_HASH"] = "h1"
    from ai.voting import record_vote
    os.environ["AI_VOTES_DIR"] = env["AI_VOTES_DIR"]
    record_vote("s1", "h1", "Codex_v1", True, "ok", "t0")
    record_vote("s1", "h1", "Codex_v2", True, "ok", "t1")
    record_vote("s1", "h1", "ClaudeSim", True, "ok", "t2")
    run_script(["promote", "s1", "--source-dir", str(staging.parent), "--dest-dir", str(active.parent)], env)
    assert active.exists()
    run_script(["pause", "s1", "--dest-dir", str(active.parent), "--paused-dir", str(paused)], env)
    assert not active.exists() and (paused / "s1").exists()

