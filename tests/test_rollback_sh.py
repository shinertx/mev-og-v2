import os
import subprocess
import tarfile
import json
import shutil
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "rollback.sh"


def run_script(args, env):
    return subprocess.run(["bash", str(SCRIPT)] + args, capture_output=True, text=True, env=env, check=True)


def test_restore_success(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    logs = tmp_path / "logs"
    state = tmp_path / "state"
    active = tmp_path / "active"
    logs.mkdir()
    state.mkdir()
    active.mkdir()
    (logs / "log.txt").write_text("log")
    (state / "state.txt").write_text("state")
    (active / "a.txt").write_text("active")
    archive = export_dir / "drp_export_test.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(logs, arcname="logs")
        tar.add(state, arcname="state")
        tar.add(active, arcname="active")
    shutil.rmtree(logs)
    shutil.rmtree(state)
    shutil.rmtree(active)
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "errors.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rollback.log"),
        "PWD": str(tmp_path)
    })
    os.chdir(tmp_path)
    run_script([f"--archive={archive}",], env)
    assert (logs / "log.txt").exists()
    assert (state / "state.txt").exists()
    assert (active / "a.txt").exists()
    entries = [json.loads(line) for line in (tmp_path / "rollback.log").read_text().splitlines()]
    assert entries[-1]["event"] == "restore"


def test_missing_archive(tmp_path):
    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "EXPORT_DIR": str(tmp_path / "export"),
        "PWD": str(tmp_path)
    })
    os.chdir(tmp_path)
    (tmp_path / "export").mkdir()
    try:
        run_script([], env)
    except subprocess.CalledProcessError:
        pass
    entries = [json.loads(line) for line in (tmp_path / "rb.log").read_text().splitlines()]
    assert entries[-1]["event"] == "failed"
    assert (tmp_path / "err.log").exists()


def test_restore_encrypted(tmp_path):
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "log.txt").write_text("log")
    archive = export_dir / "drp_export_test.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(logs, arcname="logs")
    encrypted = archive.with_suffix(archive.suffix + '.enc')
    shutil.copyfile(archive, encrypted)
    shutil.rmtree(logs)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    openssl_path = bin_dir / "openssl"
    openssl_path.write_text(
        "#!/bin/bash\n"
        "while [[ $# -gt 0 ]]; do\n"
        " case \"$1\" in\n"
        "  -in) IN=$2; shift 2;;\n"
        "  -out) OUT=$2; shift 2;;\n"
        "  *) shift;;\n"
        " esac\n"
        "done\n"
        "cp \"$IN\" \"$OUT\"\n"
    )
    openssl_path.chmod(0o755)

    env = os.environ.copy()
    env.update({
        "ERROR_LOG_FILE": str(tmp_path / "err.log"),
        "ROLLBACK_LOG_FILE": str(tmp_path / "rb.log"),
        "PWD": str(tmp_path),
        "DRP_ENC_KEY": "secret",
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
    })
    os.chdir(tmp_path)

    run_script([f"--archive={encrypted}"], env)
    assert (tmp_path / "logs" / "log.txt").exists()
    entries = [json.loads(line) for line in (tmp_path / "rb.log").read_text().splitlines()]
    assert entries[-1]["event"] == "restore"
