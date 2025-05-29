"""Unified strategy orchestrator."""

from __future__ import annotations

import argparse
import importlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List

from core.logger import StructuredLogger, log_error
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from agents.ops_agent import OpsAgent
from agents.capital_lock import CapitalLock

LOGGER = StructuredLogger("orchestrator")


# ---------------------------------------------------------------------------
def _simple_yaml_load(text: str) -> Dict[str, Any]:
    """Very small YAML subset parser used if PyYAML is unavailable."""

    data: Dict[str, Any] = {}
    stack: List[tuple[int, Dict[str, Any]]] = [(0, data)]
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        key, _, value = raw.lstrip().partition(":")
        value = value.strip()
        while stack and indent < stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if not value:
            d: Dict[str, Any] = {}
            parent[key] = d
            stack.append((indent + 1, d))
            continue
        if value == "{}":
            parent[key] = {}
        elif value.startswith("[") and value.endswith("]"):
            items = [v.strip().strip('"\'') for v in value[1:-1].split(",") if v.strip()]
            parent[key] = items
        elif value.lower() in {"true", "false"}:
            parent[key] = value.lower() == "true"
        else:
            try:
                parent[key] = int(value)
            except ValueError:
                try:
                    parent[key] = float(value)
                except ValueError:
                    parent[key] = value.strip('"\'')
    return data


# ---------------------------------------------------------------------------
def load_config(path: str) -> Dict[str, Any]:
    """Load YAML config from ``path`` using PyYAML if available."""

    try:
        import yaml  # type: ignore
    except Exception:  # pragma: no cover - optional
        yaml = None  # type: ignore
    text = Path(path).read_text()
    if yaml is not None:
        return yaml.safe_load(text)
    return _simple_yaml_load(text)


# ---------------------------------------------------------------------------
class StrategyOrchestrator:
    """Load strategies and enforce runtime gating."""

    def __init__(self, config_path: str, *, dry_run: bool | None = None) -> None:
        self.config = load_config(config_path)
        self.dry_run = dry_run if dry_run is not None else self.config.get("mode") != "live"
        risk = self.config.get("risk", {})
        capital = float(self.config.get("starting_capital", 0))
        self.capital_lock = CapitalLock(
            float(risk.get("max_drawdown_pct", 0)),
            float(risk.get("max_loss_usd", 0)),
            capital,
        )
        checks = {
            "kill_switch": lambda: not kill_switch_triggered(),
            "capital_lock": self.capital_lock.trade_allowed,
        }
        self.ops_agent = OpsAgent(checks)
        self.strategy_ids: List[str] = self.config.get("alpha", {}).get("enabled", [])
        self.strategy_params: Dict[str, Any] = self.config.get("alpha", {}).get("params", {})
        self.strategies: Dict[str, Any] = {}
        self._load_strategies()

    # ---------------------------------------------------------------
    def _load_strategies(self) -> None:
        for sid in self.strategy_ids:
            try:
                module = importlib.import_module(f"strategies.{sid}.strategy")
                cls = getattr(module, [n for n in dir(module) if n[0].isupper()][0])
                params = self.strategy_params.get(sid, {})
                strat = cls(**params)
                setattr(strat, "wallet_address", self.config.get("wallet_address"))
                setattr(strat, "ops_agent", self.ops_agent)
                setattr(strat, "capital_lock", self.capital_lock)
                self.strategies[sid] = strat
                LOGGER.log("strategy_loaded", strategy_id=sid, risk_level="low")
            except Exception as exc:
                log_error("orchestrator", str(exc), strategy_id=sid, event="load_fail")

    # ---------------------------------------------------------------
    def _snapshot_state(self) -> None:
        cmd = ["bash", "scripts/export_state.sh"]
        if self.dry_run:
            cmd.append("--dry-run")
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            log_error("orchestrator", "export_state.sh missing", event="snapshot_fail")
        except subprocess.CalledProcessError as exc:
            log_error("orchestrator", f"snapshot fail: {exc.stderr}", event="snapshot_fail")

    # ---------------------------------------------------------------
    def run_once(self) -> bool:
        if kill_switch_triggered():
            record_kill_event("orchestrator")
            LOGGER.log("kill_switch", risk_level="high")
            return False

        if self.config.get("capital_lock_enabled", True) and not self.capital_lock.trade_allowed():
            LOGGER.log("capital_lock", risk_level="high")
            return False

        self.ops_agent.run_checks()
        if self.ops_agent.paused:
            LOGGER.log("ops_pause", risk_level="high")
            return False

        if self.config.get("mode") == "live" and os.getenv("FOUNDER_APPROVED") != "1":
            LOGGER.log("founder_block", risk_level="high")
            return False

        for sid, strat in self.strategies.items():
            try:
                strat.run_once()
            except Exception as exc:  # pragma: no cover - runtime
                log_error("orchestrator", str(exc), strategy_id=sid, event="exec_fail")
                self.ops_agent.auto_pause("strategy_fail")
                return False

        self._snapshot_state()
        LOGGER.log("iteration_complete", risk_level="low")
        return True

    # ---------------------------------------------------------------
    def run_live_loop(self, interval: int = 5) -> None:
        while True:
            cont = self.run_once()
            if not cont:
                LOGGER.log("halt", risk_level="high")
                break
            if self.dry_run:
                break
            time.sleep(interval)


# ---------------------------------------------------------------------------
def main() -> None:  # pragma: no cover - CLI thin wrapper
    parser = argparse.ArgumentParser(description="Strategy orchestrator")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--dry-run", action="store_true", help="Run a single dry iteration")
    parser.add_argument("--live", action="store_true", help="Force live mode")
    parser.add_argument("--health", action="store_true", help="Only run health checks")
    args = parser.parse_args()

    dry = args.dry_run or os.getenv("DRY_RUN") == "1" or (not args.live and load_config(args.config).get("mode") != "live")
    orchestrator = StrategyOrchestrator(args.config, dry_run=dry)
    if args.health:
        orchestrator.ops_agent.run_checks()
        return
    orchestrator.run_live_loop()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
