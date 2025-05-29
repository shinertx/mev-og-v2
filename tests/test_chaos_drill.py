import os
import subprocess
import sys
from pathlib import Path
import json

SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "sim_harness" / "chaos_drill.py"


def test_chaos_drill(tmp_path):
    # prepare minimal state
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "x.log").write_text("log")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "x.txt").write_text("state")
    (tmp_path / "active").mkdir()
    (tmp_path / "active" / "a.txt").write_text("active")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "k.txt").write_text("k")

    env = os.environ.copy()
    env.update({
        "EXPORT_DIR": str(tmp_path / "export"),
        "EXPORT_LOG_FILE": str(tmp_path / "export_log.json"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rollback.log"),
        "ERROR_LOG_FILE": str(tmp_path / "errors.log"),
        "KILL_SWITCH_LOG_FILE": str(tmp_path / "kill_log.json"),
        "KILL_SWITCH_FLAG_FILE": str(tmp_path / "flag.txt"),
        "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
        "PWD": str(tmp_path),
    })
    subprocess.run([sys.executable, str(SCRIPT)], check=True, env=env, text=True)

    exports = list((tmp_path / "export").glob("drp_export_*.tar.gz"))
    assert len(exports) >= 9
    assert (tmp_path / "rollback.log").exists()
    with open(tmp_path / "export_log.json") as fh:
        lines = [json.loads(line) for line in fh]
    assert any(e.get("event") == "export" for e in lines)

    metrics = json.loads(Path(tmp_path / "logs" / "drill_metrics.json").read_text())
    assert metrics["dex_adapter"]["failures"] >= 1
