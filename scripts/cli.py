"""Developer utility commands for linting, tests and validation."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _run(cmd: list[str]) -> int:
    return subprocess.call(cmd, cwd=ROOT)


def lint() -> None:
    sys.exit(_run(["flake8", "."]))


def type_check() -> None:
    sys.exit(_run(["mypy", "--config-file", "mypy.ini", "."]))


def tests() -> None:
    sys.exit(_run(["pytest", "-v"]))


def sim_harness() -> None:
    target = os.getenv("SIM_TARGET", "strategies/cross_domain_arb")
    sys.exit(_run(["bash", "scripts/simulate_fork.sh", f"--target={target}"]))


def mutate() -> None:
    sys.exit(_run([sys.executable, "ai/mutator/main.py"]))


def audit() -> None:
    log = os.getenv("AUDIT_LOG", "logs/export_state.json")
    sys.exit(_run([sys.executable, "ai/audit_agent.py", "--mode=offline", "--logs", log]))


def export_state() -> None:
    args = ["bash", "scripts/export_state.sh"]
    if os.getenv("DRY_RUN", "1") == "1":
        args.append("--dry-run")
    sys.exit(_run(args))


if __name__ == "__main__":
    print("Use `poetry run <command>` to execute utility commands")
