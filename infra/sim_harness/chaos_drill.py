#!/usr/bin/env python3.11
"""Automated chaos/disaster recovery drill harness."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import tarfile
from pathlib import Path

from agents.ops_agent import OpsAgent
from core.logger import StructuredLogger, make_json_safe
from core.tx_engine.kill_switch import flag_file, init_kill_switch
from adapters import (
    BridgeAdapter,
    CEXAdapter,
    DEXAdapter,
    FlashloanAdapter,
)
from infra.sim_harness import start_metrics
from core import metrics
from ai.intent_ghost import ghost_intent
from core.node_selector import NodeSelector
from core.tx_engine.nonce_manager import NonceManager
from strategies.l3_sequencer_mev.strategy import L3SequencerMEV

EXPORT_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "export_state.sh"
ROLLBACK_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rollback.sh"

LOGGER = StructuredLogger("chaos_drill")
DRILL_METRICS_FILE = Path(os.getenv("CHAOS_METRICS", "logs/drill_metrics.json"))

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|private[_-]?key)"),
    re.compile(r"0x[a-fA-F0-9]{64}"),
]


def _run(cmd: list[str], env: dict[str, str]) -> None:
    result = subprocess.run(cmd, text=True, env=env, capture_output=True)
    LOGGER.log(
        "cmd_run",
        risk_level="low",
        cmd=" ".join(cmd),
        returncode=result.returncode,
    )
    if result.returncode != 0:
        LOGGER.log(
            "cmd_fail",
            risk_level="high",
            cmd=" ".join(cmd),
            error=result.stderr,
        )
        raise subprocess.CalledProcessError(result.returncode, cmd)


def _export_and_restore(env: dict[str, str]) -> None:
    LOGGER.log("export", risk_level="low")
    _run(["bash", str(EXPORT_SCRIPT)], env)
    LOGGER.log("restore", risk_level="low")
    _run(["bash", str(ROLLBACK_SCRIPT)], env)
    _check_for_secrets(env)
    time.sleep(1)


def _update_metrics(module: str) -> None:
    metrics: dict[str, dict[str, int]] = {}
    if DRILL_METRICS_FILE.exists():
        try:
            metrics = json.loads(DRILL_METRICS_FILE.read_text())
        except Exception:
            metrics = {}
    metrics.setdefault(module, {"failures": 0})
    metrics[module]["failures"] += 1
    DRILL_METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    DRILL_METRICS_FILE.write_text(json.dumps(make_json_safe(metrics), indent=2))
    try:
        metrics_mod = metrics  # alias to satisfy lint
        metrics_mod.record_error()
    except Exception:
        pass


def _scan_file(path: Path) -> None:
    try:
        data = path.read_text(errors="ignore")
    except Exception:
        return
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise RuntimeError(f"Secret detected in {path}")


def _check_for_secrets(env: dict[str, str]) -> None:
    export_dir = Path(env.get("EXPORT_DIR", "export"))
    for p in export_dir.rglob("*"):
        if p.is_file():
            if p.suffixes[-2:] == [".tar", ".gz"] or p.suffix == ".tar.gz":
                with tarfile.open(p) as tar:
                    for m in tar.getmembers():
                        if m.isfile():
                            f = tar.extractfile(m)
                            if f:
                                data = f.read().decode(errors="ignore")
                                for pattern in SECRET_PATTERNS:
                                    if pattern.search(data):
                                        raise RuntimeError(f"Secret detected in archive {p}::{m.name}")
            else:
                _scan_file(p)
    _scan_file(LOGGER.path)


def _drill_kill_switch(env: dict[str, str]) -> None:
    init_kill_switch()
    ff = flag_file()
    ff.parent.mkdir(parents=True, exist_ok=True)
    ff.write_text("1")
    LOGGER.log("kill_switch_forced", risk_level="high")
    _export_and_restore(env)


def _drill_lost_agent(env: dict[str, str]) -> None:
    ops = OpsAgent({})
    ops.auto_pause(reason="lost_agent")
    LOGGER.log("lost_agent", risk_level="high")
    _export_and_restore(env)


def _drill_adapter_fail(env: dict[str, str]) -> None:
    try:
        adapter = DEXAdapter("http://127.0.0.1:1")  # type: ignore[misc]
        adapter.get_quote("ETH", "USDC", 1)
    except Exception:
        LOGGER.log("adapter_fail", risk_level="high")
        _update_metrics("dex_adapter")
    _export_and_restore(env)


def _drill_bridge_fail(env: dict[str, str]) -> None:
    try:
        adapter = BridgeAdapter("http://127.0.0.1:1")  # type: ignore[misc]
        adapter.bridge("eth", "arb", "ETH", 1)
    except Exception:
        LOGGER.log("bridge_fail", risk_level="high")
        _update_metrics("bridge_adapter")
    _export_and_restore(env)


def _drill_cex_fail(env: dict[str, str]) -> None:
    try:
        adapter = CEXAdapter("http://127.0.0.1:1", "bad")  # type: ignore[misc]
        adapter.place_order("buy", 1, 1)
    except Exception:
        LOGGER.log("cex_fail", risk_level="high")
        _update_metrics("cex_adapter")
    _export_and_restore(env)


def _drill_flashloan_fail(env: dict[str, str]) -> None:
    try:
        adapter = FlashloanAdapter("http://127.0.0.1:1")  # type: ignore[misc]
        adapter.trigger("ETH", 1)
    except Exception:
        LOGGER.log("flashloan_fail", risk_level="high")
        _update_metrics("flashloan_adapter")
    _export_and_restore(env)


def _drill_intent_fail(env: dict[str, str]) -> None:
    try:
        ghost_intent("http://127.0.0.1:1", {"intent_id": "x"})
    except Exception:
        LOGGER.log("intent_fail", risk_level="high")
        _update_metrics("intent")
    _export_and_restore(env)


def _drill_node_fail(env: dict[str, str]) -> None:
    try:
        selector = NodeSelector({})
        selector.best()
    except Exception:
        LOGGER.log("node_fail", risk_level="high")
        _update_metrics("node")
    _export_and_restore(env)


def _drill_sequencer_fail(env: dict[str, str]) -> None:
    try:
        from strategies.l3_sequencer_mev.strategy import L3SequencerMEV

        strat = L3SequencerMEV({})
        strat._bundle_and_send("test")
    except Exception:
        LOGGER.log("sequencer_fail", risk_level="high")
        _update_metrics("sequencer")
    _export_and_restore(env)


def _drill_reorg_fail(env: dict[str, str]) -> None:
    try:
        strat = L3SequencerMEV({})
        strat.last_block = 5
        strat._detect_opportunity({"a": 1.0, "b": 2.0}, block=3, timestamp=1)
    except Exception:
        pass
    LOGGER.log("reorg_fail", risk_level="high")
    _update_metrics("reorg")
    _export_and_restore(env)


def _drill_nonce_gap(env: dict[str, str]) -> None:
    nm = NonceManager(None, cache_file="state/nc.json", log_file="logs/nl.json")
    nm.update_nonce("0xabc", 1)
    nm.update_nonce("0xabc", 5)
    LOGGER.log("nonce_gap", risk_level="high")
    _update_metrics("nonce")
    _export_and_restore(env)


def _drill_rpc_fail(env: dict[str, str]) -> None:
    class BadWeb3:
        class Eth:
            def get_transaction_count(self, address: str) -> int:
                raise RuntimeError("rpc fail")

        eth = Eth()

    nm = NonceManager(BadWeb3(), cache_file="state/rpc.json", log_file="logs/rpc.json")
    try:
        nm.get_nonce("0xabc")
    except Exception:
        LOGGER.log("rpc_fail", risk_level="high")
        _update_metrics("rpc")
    _export_and_restore(env)


def _drill_data_dos(env: dict[str, str]) -> None:
    try:
        adapter = DEXAdapter("http://127.0.0.1:1")  # type: ignore[misc]
        adapter.get_quote("ETH", "USDC", 1, simulate_failure="data_poison")
    except Exception:
        LOGGER.log("data_dos", risk_level="high")
        _update_metrics("dos")
    _export_and_restore(env)


def run_drill() -> None:
    start_metrics()
    env = os.environ.copy()
    _drill_kill_switch(env)
    _drill_lost_agent(env)
    _drill_adapter_fail(env)
    _drill_bridge_fail(env)
    _drill_cex_fail(env)
    _drill_flashloan_fail(env)
    _drill_intent_fail(env)
    _drill_node_fail(env)
    _drill_sequencer_fail(env)
    _drill_reorg_fail(env)
    _drill_nonce_gap(env)
    _drill_rpc_fail(env)
    _drill_data_dos(env)


if __name__ == "__main__":
    run_drill()
