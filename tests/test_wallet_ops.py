import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "wallet_ops.py"


def run_script(
    args: list[str],
    env: dict[str, str],
    input_data: str = "",
) -> subprocess.CompletedProcess[str]:
    env = env.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    return subprocess.run(
        [sys.executable, str(SCRIPT)] + args,
        input=input_data,
        capture_output=True,
        text=True,
        env=env,
    )


def test_fund_dry_run(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "FOUNDER_TOKEN": "wallet_ops:9999999999",
            "WALLET_OPS_LOG": str(tmp_path / "wallet.json"),
            "EXPORT_LOG_FILE": str(tmp_path / "export.json"),
            "EXPORT_DIR": str(tmp_path / "export"),
            "PWD": str(tmp_path),
        }
    )
    result = run_script(
        [
            "--dry-run",
            "fund",
            "--from",
            "0xabc",
            "--to",
            "0xdef",
            "--amount",
            "1",
        ],
        env,
    )
    assert result.returncode == 0
    logs = [json.loads(line) for line in Path(env["WALLET_OPS_LOG"]).read_text().splitlines()]
    assert logs[-1]["event"] == "fund"
    export_entries = [json.loads(line) for line in Path(env["EXPORT_LOG_FILE"]).read_text().splitlines()]
    assert len(export_entries) == 2


def test_no_approval(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "WALLET_OPS_LOG": str(tmp_path / "wallet.json"),
            "EXPORT_LOG_FILE": str(tmp_path / "export.json"),
            "EXPORT_DIR": str(tmp_path / "export"),
            "PWD": str(tmp_path),
        }
    )
    result = run_script(
        [
            "--dry-run",
            "fund",
            "--from",
            "0xabc",
            "--to",
            "0xdef",
            "--amount",
            "1",
        ],
        env,
        input_data="n\n",
    )
    assert result.returncode != 0
    logs = [json.loads(line) for line in Path(env["WALLET_OPS_LOG"]).read_text().splitlines()]
    assert logs[-1]["event"] == "founder_confirm"
    assert logs[-1]["approved"] is False


def test_tx_fail(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "FOUNDER_TOKEN": "wallet_ops:9999999999",
            "WALLET_OPS_LOG": str(tmp_path / "wallet.json"),
            "EXPORT_LOG_FILE": str(tmp_path / "export.json"),
            "EXPORT_DIR": str(tmp_path / "export"),
            "PWD": str(tmp_path),
            "WALLET_OPS_TX_MODE": "fail",
        }
    )
    result = run_script(
        [
            "fund",
            "--from",
            "0xabc",
            "--to",
            "0xdef",
            "--amount",
            "1",
        ],
        env,
    )
    assert result.returncode != 0
    logs = [json.loads(line) for line in Path(env["WALLET_OPS_LOG"]).read_text().splitlines()]
    assert logs[-1]["event"] == "fund_fail"
    assert logs[-1]["error"]


def test_insufficient_funds(tmp_path: Path) -> None:
    os.chdir(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "FOUNDER_TOKEN": "wallet_ops:9999999999",
            "WALLET_OPS_LOG": str(tmp_path / "wallet.json"),
            "EXPORT_LOG_FILE": str(tmp_path / "export.json"),
            "EXPORT_DIR": str(tmp_path / "export"),
            "PWD": str(tmp_path),
            "WALLET_OPS_TX_MODE": "insufficient",
        }
    )
    result = run_script(
        [
            "withdraw-all",
            "--from",
            "0xabc",
            "--to",
            "0xdef",
        ],
        env,
    )
    assert result.returncode != 0
    logs = [json.loads(line) for line in Path(env["WALLET_OPS_LOG"]).read_text().splitlines()]
    assert logs[-1]["event"] == "withdraw-all_fail"
    assert "insufficient" in logs[-1]["error"]

