"""Tests for the export_state.sh disaster recovery script."""

import os
import subprocess
from pathlib import Path
import json
import tarfile

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "export_state.sh"


def run_script(args, env):
    return subprocess.run(["bash", str(SCRIPT)] + args, capture_output=True, text=True, env=env, check=True)


def test_export_and_clean(tmp_path):
    logs_dir = tmp_path / "logs"
    state_dir = tmp_path / "state"
    logs_dir.mkdir()
    state_dir.mkdir()
    (logs_dir / "log.txt").write_text("log")
    (state_dir / "state.txt").write_text("state")

    export_dir = tmp_path / "export"
    log_file = tmp_path / "export_log.json"

    env = os.environ.copy()
    env.update({
        "EXPORT_DIR": str(export_dir),
        "EXPORT_LOG_FILE": str(log_file),
        "PWD": str(tmp_path)
    })
    os.chdir(tmp_path)

    run_script([], env)
    archives = list(export_dir.glob("drp_export_*.tar.gz"))
    assert len(archives) == 1
    with tarfile.open(archives[0], "r:gz") as tar:
        names = tar.getnames()
        assert "logs/log.txt" in names or "state/state.txt" in names

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "export"

    run_script(["--clean"], env)
    assert not any(logs_dir.iterdir())
    assert not any(state_dir.iterdir())
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "clean"


def test_dry_run(tmp_path):
    export_dir = tmp_path / "export"
    log_file = tmp_path / "export_log.json"
    env = os.environ.copy()
    env.update({
        "EXPORT_DIR": str(export_dir),
        "EXPORT_LOG_FILE": str(log_file),
        "PWD": str(tmp_path)
    })
    os.chdir(tmp_path)

    result = run_script(["--dry-run"], env)
    assert "DRY RUN" in result.stdout
    assert not export_dir.exists()
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "dry-run"
