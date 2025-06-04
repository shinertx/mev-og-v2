#!/usr/bin/env python3.11
"""Scheduled chaos injection harness."""

from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict

from agents.ops_agent import OpsAgent
from core.logger import StructuredLogger, make_json_safe
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from adapters import DEXAdapter, BridgeAdapter, CEXAdapter, FlashloanAdapter
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger(
    "chaos_scheduler", log_file=os.getenv("CHAOS_SCHED_LOG", "logs/chaos_scheduler.json")
)

OPS = OpsAgent({})


ADAPTER_FUNCS: Dict[str, Callable[[str], Dict[str, Any]]] = {
    "dex": lambda mode: DEXAdapter("http://bad", alt_api_urls=["http://alt"], ops_agent=OPS).get_quote("ETH", "USDC", 1, simulate_failure=mode),
    "bridge": lambda mode: BridgeAdapter("http://bad", alt_api_urls=["http://alt"], ops_agent=OPS).bridge("eth", "arb", "ETH", 1, simulate_failure=mode),
    "cex": lambda mode: CEXAdapter("http://bad", "k", alt_api_urls=["http://alt"], ops_agent=OPS).get_balance(simulate_failure=mode),
    "flashloan": lambda mode: FlashloanAdapter("http://bad", alt_api_urls=["http://alt"], ops_agent=OPS).trigger("ETH", 1, simulate_failure=mode),
}


def _update_metrics(adapter: str) -> None:
    metrics_file = Path(os.getenv("CHAOS_METRICS", "logs/drill_metrics.json"))
    metrics: Dict[str, Dict[str, int]] = {}
    if metrics_file.exists():
        try:
            metrics = json.loads(metrics_file.read_text())
        except Exception:
            metrics = {}
    metrics.setdefault(adapter, {"failures": 0})
    metrics[adapter]["failures"] += 1
    metrics_file.parent.mkdir(parents=True, exist_ok=True)
    metrics_file.write_text(json.dumps(make_json_safe(metrics), indent=2))


def run_once() -> None:
    adapters = [a.strip() for a in os.getenv("CHAOS_ADAPTERS", "dex,bridge,cex,flashloan").split(",") if a.strip()]
    modes = [m.strip() for m in os.getenv("CHAOS_MODES", "network,rpc,downtime,data_poison").split(",") if m.strip()]
    adapter = random.choice(adapters)
    mode = random.choice(modes)
    LOGGER.log("chaos_start", adapter=adapter, mode=mode)
    try:
        ADAPTER_FUNCS[adapter](mode)
        fallback = "success"
    except Exception as exc:  # pragma: no cover - runtime
        fallback = "fail"
        OPS.notify(f"chaos_fail:{adapter}:{exc}")
        os.environ["OPS_CRITICAL_EVENT"] = "1"
    _update_metrics(adapter)
    log_mutation("adapter_chaos", adapter=adapter, failure=mode, fallback=fallback)
    LOGGER.log("chaos_complete", adapter=adapter, mode=mode, fallback=fallback)


def main() -> None:
    interval = int(os.getenv("CHAOS_INTERVAL", "600"))
    once = os.getenv("CHAOS_ONCE") == "1"
    while True:
        if kill_switch_triggered():
            record_kill_event("chaos_scheduler")
            break
        run_once()
        if once:
            break
        time.sleep(interval)


if __name__ == "__main__":
    main()
