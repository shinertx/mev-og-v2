import os
import subprocess
import tarfile
import time
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollback.sh"


def run_script(args, env):
    return subprocess.run(["bash", str(SCRIPT)] + args, capture_output=True, text=True, env=env, check=True)


def test_drp_restore_time(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "log.txt").write_text("x")
    archive = export_dir / "drp_test.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(logs, arcname="logs")
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "PWD": str(tmp_path)
    })
    start = time.time()
    run_script([f"--archive={archive}"], env)
    duration = time.time() - start
    assert duration < 60
    assert (logs / "log.txt").exists()


def test_invalid_archive_fails_fast(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.txt").write_text("x")
    archive = export_dir / "bad.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(bad / "x.txt", arcname="../../x.txt")
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "PWD": str(tmp_path),
    })
    start = time.time()
    with pytest.raises(subprocess.CalledProcessError):
        run_script([f"--archive={archive}"], env)
    assert time.time() - start < 60
    assert not (tmp_path / "x.txt").exists()

