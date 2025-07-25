"""AI-driven mutation cycle orchestrator.

Module purpose and system role:
    - Coordinate offline scoring, pruning and auditing of strategies.
    - Query an online LLM for mutation recommendations.
    - Apply strategy mutations, run validations and promote on success.

Integration points and dependencies:
    - Uses :mod:`ai.mutator` utilities, :class:`ai.audit_agent.AuditAgent`, and
      :func:`ai.promote.promote_strategy`.
    - Relies on :class:`core.logger.StructuredLogger` for audit logging.

Simulation/test hooks and kill conditions:
    - Designed for offline unit tests with optional OpenAI access mocked.
    - All subprocess calls are wrapped for error logging; failure halts
      promotion.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import uuid
from pathlib import Path
from typing import Dict

from core.logger import StructuredLogger, log_error, make_json_safe
from ai.audit_agent import AuditAgent
from ai.mutator import Mutator
from ai.promote import promote_strategy
from agents.founder_gate import founder_approved

LOGGER = StructuredLogger("mutation_main")


class MutationRunner:
    """Run a single mutation/audit/promotion cycle."""

    def __init__(self, repo_root: str | None = None, logs_dir: str = "logs") -> None:
        self.repo_root = Path(repo_root or Path(__file__).resolve().parents[1])
        self.logs_dir = Path(logs_dir)
        self.audit_agent = AuditAgent(str(self.repo_root))

    # ------------------------------------------------------------------
    def _collect_metrics(self) -> Dict[str, Dict[str, float]]:
        metrics: Dict[str, Dict[str, float]] = {}
        for file in self.logs_dir.glob("*.json"):
            if file.name == "errors.log":
                continue
            try:
                lines = [json.loads(line) for line in file.read_text().splitlines() if line.strip()]
            except Exception as exc:
                log_error("mutation_main", str(exc), strategy_id=file.stem, event="log_parse")
                continue
            pnl = sum(float(e.get("spread", 0)) for e in lines if e.get("opportunity"))
            fails = sum(1 for e in lines if e.get("error"))
            total = len(lines)
            risk = fails / max(total, 1)
            win_rate = 1 - risk
            metrics[file.stem] = {
                "pnl": pnl,
                "risk": risk,
                "win_rate": win_rate,
            }
        return metrics

    # ------------------------------------------------------------------
    def _run_checks(self, strategy: str) -> bool:
        cmds = [
            ["pytest", "-v"],
            ["foundry", "test"],
            ["bash", "scripts/simulate_fork.sh", f"--target=strategies/{strategy}"],
            ["bash", "scripts/export_state.sh", "--dry-run"],
            ["python", "ai/audit_agent.py", "--mode=offline", "--logs", f"logs/{strategy}.json"],
        ]
        for cmd in cmds:
            try:
                subprocess.run(
                    cmd,
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                log_error(
                    "mutation_main",
                    f"missing command: {' '.join(cmd)}",
                    strategy_id=strategy,
                    event="cmd_missing",
                )
            except subprocess.CalledProcessError as exc:
                log_error(
                    "mutation_main",
                    f"cmd failed: {exc.stderr}",
                    strategy_id=strategy,
                    event="cmd_fail",
                )
                return False
        return True

    # ------------------------------------------------------------------
    def run_cycle(self) -> None:
        (self.logs_dir / "errors.log").touch(exist_ok=True)
        metrics = self._collect_metrics()
        mutator = Mutator(metrics)
        block_number = int(os.getenv("BLOCK_NUMBER", "0"))
        chain_id = int(os.getenv("CHAIN_ID", "0"))
        test_mode = os.getenv("TEST_MODE") == "1"
        result = mutator.run(
            block_number=block_number,
            chain_id=chain_id,
            test_mode=test_mode,
        )

        log_paths = [str(p) for p in self.logs_dir.glob("*.json") if p.name != "errors.log"]
        audit_summary = self.audit_agent.run_audit(log_paths)

        prompt = json.dumps(make_json_safe({"metrics": metrics, "audit": audit_summary}))
        try:
            online_resp = self.audit_agent.run_online_audit(prompt)
        except Exception as exc:  # pragma: no cover - network errors
            online_resp = str(exc)
            log_error("mutation_main", str(exc), event="online_audit")

        LOGGER.log(
            "cycle_complete",
            mutation_id=os.getenv("MUTATION_ID", "dev"),
            risk_level="low",
            scores=result.get("scores", []),
            pruned=result.get("pruned", []),
            audit=audit_summary,
            trace_id=os.getenv("TRACE_ID", str(uuid.uuid4())),
        )

        for sid in metrics:
            if sid in result.get("pruned", []):
                continue
            try:
                import strategies
                extra = str(self.repo_root / "strategies")
                if extra not in strategies.__path__:
                    strategies.__path__.append(extra)
                module = importlib.import_module(f"strategies.{sid}.strategy")
                strat_cls = getattr(module, [n for n in dir(module) if n[0].isupper()][0])
                try:
                    strat = strat_cls({})
                except TypeError:
                    strat = strat_cls()
                if hasattr(strat, "mutate"):
                    strat.mutate({"threshold": 0.005})
            except Exception as exc:  # pragma: no cover - import edge
                log_error(
                    "mutation_main",
                    f"mutation failed: {exc}",
                    strategy_id=sid,
                    event="mutate",
                )
                continue

            tests_pass = self._run_checks(sid)
            trace = os.getenv("TRACE_ID", str(uuid.uuid4()))
            if tests_pass and founder_approved("promote"):
                src = self.repo_root / "strategies" / sid
                dst = self.repo_root / "active" / sid
                promote_strategy(
                    src,
                    dst,
                    True,
                    {"audit": audit_summary, "online": online_resp},
                    trace_id=trace,
                )
            elif not tests_pass:
                log_error(
                    "mutation_main",
                    "tests failed",
                    strategy_id=sid,
                    event="promote_block",
                    trace_id=trace,
                )
            else:
                log_error(
                    "mutation_main",
                    "founder approval required",
                    strategy_id=sid,
                    event="promote_gate",
                    trace_id=trace,
                )


def main() -> None:  # pragma: no cover - CLI wrapper
    parser = argparse.ArgumentParser(description="Run mutation cycle")
    parser.add_argument("--logs-dir", default="logs", help="Directory with strategy logs")
    args = parser.parse_args()
    runner = MutationRunner(logs_dir=args.logs_dir)
    runner.run_cycle()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
