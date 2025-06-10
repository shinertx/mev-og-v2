import os
import subprocess
import tarfile
import io
import time
import json
from pathlib import Path
import pytest
from agents.drp_agent import DRPAgent


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
    err_lines = (tmp_path / "err.log").read_text().splitlines()
    assert "unsafe_path" in err_lines[-1]
    entries = [json.loads(line) for line in (tmp_path / "rb.log").read_text().splitlines()]
    assert entries[-1]["event"] == "failed"


def test_absolute_path_rejected(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "x.txt").write_text("x")
    archive = export_dir / "abs.tar.gz"
    with tarfile.open(archive, "w:gz") as tar, open(bad / "x.txt", "rb") as fh:
        info = tarfile.TarInfo("/abs.txt")
        fh_data = fh.read()
        info.size = len(fh_data)
        tar.addfile(info, io.BytesIO(fh_data))
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "PWD": str(tmp_path),
    })
    with pytest.raises(subprocess.CalledProcessError):
        run_script([f"--archive={archive}"], env)
    err_lines = (tmp_path / "err.log").read_text().splitlines()
    assert "unsafe_path" in err_lines[-1]
    entries = [json.loads(line) for line in (tmp_path / "rb.log").read_text().splitlines()]
    assert entries[-1]["event"] == "failed"


def test_invalid_chars_rejected(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    archive = export_dir / "invalid.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        data = b"x"
        info = tarfile.TarInfo("logs/bad:evil.txt")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "PWD": str(tmp_path),
    })
    with pytest.raises(subprocess.CalledProcessError):
        run_script([f"--archive={archive}"], env)
    err_lines = (tmp_path / "err.log").read_text().splitlines()
    assert "unsafe_path" in err_lines[-1]
    entries = [json.loads(line) for line in (tmp_path / "rb.log").read_text().splitlines()]
    assert entries[-1]["event"] == "failed"


def _make_archive(export_dir: Path) -> Path:
    logs = export_dir.parent / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "log.txt").write_text("x")
    archive = export_dir / "drp_export_test.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(logs, arcname="logs")
    return archive


def test_recovery_window(tmp_path, monkeypatch):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    archive = _make_archive(export_dir)
    old = time.time() - 7200
    os.utime(archive, (old, old))
    agent = DRPAgent(ready=False)

    called: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(list(a[0])))
    agent.auto_recover(export_dir=str(export_dir), timeout=3600)
    assert called

    called.clear()
    archive = _make_archive(export_dir)
    agent.ready = False
    agent.auto_recover(export_dir=str(export_dir), timeout=3600)
    assert not called


def test_record_export_and_is_ready(tmp_path, monkeypatch):
    log_file = tmp_path / "drp.json"
    monkeypatch.setenv("DRP_AGENT_LOG", str(log_file))
    agent = DRPAgent(ready=False)

    agent.record_export(True)
    assert agent.is_ready()
    lines = [json.loads(entry) for entry in log_file.read_text().splitlines()]
    assert lines[-1]["event"] == "export_ok"

    agent.record_export(False)
    assert not agent.is_ready()
    lines = [json.loads(entry) for entry in log_file.read_text().splitlines()]
    assert lines[-1]["event"] == "export_fail"


def test_auto_recover_updates_state(tmp_path, monkeypatch):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    archive = _make_archive(export_dir)
    old = time.time() - 7200
    os.utime(archive, (old, old))
    log_file = tmp_path / "drp.json"
    monkeypatch.setenv("DRP_AGENT_LOG", str(log_file))

    called: list[list[str]] = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: called.append(list(a[0])))

    agent = DRPAgent(ready=False)
    agent.auto_recover(export_dir=str(export_dir), timeout=3600)
    assert called
    assert agent.is_ready()
    lines = [json.loads(entry) for entry in log_file.read_text().splitlines()]
    assert lines[-1]["event"] == "auto_rollback"

