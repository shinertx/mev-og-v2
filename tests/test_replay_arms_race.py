import json
import subprocess
from pathlib import Path
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "replay_arms_race.py"


def test_replay(tmp_path):
    data = [{"hash": "0x1", "profit": 1}, {"hash": "0x2", "profit": -1}]
    log = tmp_path / "txs.json"
    log.write_text(json.dumps(data))
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    res = subprocess.run([sys.executable, str(SCRIPT), "--log", str(log)], capture_output=True, text=True, env=env, check=True)
    out = json.loads(res.stdout.strip())
    assert out["wins"] == 1


def test_missing_log_file(tmp_path):
    log = tmp_path / "missing.json"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    res = subprocess.run([
        sys.executable,
        str(SCRIPT),
        "--log",
        str(log),
    ], capture_output=True, text=True, env=env, check=True)
    out = json.loads(res.stdout.strip())
    assert out == {"wins": 0, "losses": 0}
    assert log.exists()
