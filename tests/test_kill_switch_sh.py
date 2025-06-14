"""Integration tests for kill_switch.sh script."""

import json
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "kill_switch.sh"

def run_script(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT)] + args,
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )


def test_trigger_and_clean(tmp_path: Path) -> None:
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"

    env = os.environ.copy()
    env.update({
        "KILL_SWITCH_LOG_FILE": str(log_file),
        "KILL_SWITCH_FLAG_FILE": str(flag_file),
    })

    run_script([], env)
    assert flag_file.exists()

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "trigger"

    run_script(["--clean"], env)
    assert not flag_file.exists()

    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "clean"


def test_dry_run(tmp_path: Path) -> None:
    log_file = tmp_path / "log.json"
    flag_file = tmp_path / "flag.txt"
    env = os.environ.copy()
    env.update({
        "KILL_SWITCH_LOG_FILE": str(log_file),
        "KILL_SWITCH_FLAG_FILE": str(flag_file),
    })

    result = run_script(["--dry-run"], env)
    assert "DRY RUN" in result.stdout
    assert not flag_file.exists()
    entries = [json.loads(line) for line in log_file.read_text().splitlines()]
    assert entries[-1]["mode"] == "dry-run"
