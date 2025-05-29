import json
import os
import random
import time
from pathlib import Path

from adapters import BridgeAdapter, CEXAdapter, DEXAdapter, FlashloanAdapter
from agents.ops_agent import OpsAgent
from ai.mutation_log import log_mutation
from core.logger import StructuredLogger, make_json_safe

LOGGER = StructuredLogger("chaos_scheduler")
LOG_FILE = Path(os.getenv("CHAOS_LOG", "logs/chaos_scheduler.json"))
METRICS_FILE = Path(os.getenv("CHAOS_METRICS", "logs/drill_metrics.json"))

# ---------------------------------------------------------------------------

def _update_metrics(adapter: str) -> None:
    metrics: dict[str, dict[str, int]] = {}
    if METRICS_FILE.exists():
        try:
            metrics = json.loads(METRICS_FILE.read_text())
        except Exception:
            metrics = {}
    metrics.setdefault(adapter, {"failures": 0})["failures"] += 1
    METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    METRICS_FILE.write_text(json.dumps(make_json_safe(metrics), indent=2))


# ---------------------------------------------------------------------------

def _inject(adapter: str, mode: str, ops: OpsAgent) -> None:
    LOGGER.log("inject", adapter=adapter, mode=mode)
    try:
        if adapter == "dex":
            DEXAdapter("http://bad", alt_api_urls=["http://alt"], ops_agent=ops).get_quote(
                "ETH", "USDC", 1, simulate_failure=mode
            )
        elif adapter == "bridge":
            BridgeAdapter("http://bad", alt_api_urls=["http://alt"], ops_agent=ops).bridge(
                "eth", "arb", "ETH", 1, simulate_failure=mode
            )
        elif adapter == "cex":
            CEXAdapter(
                "http://bad",
                "k",
                alt_api_urls=["http://alt"],
                ops_agent=ops,
            ).get_balance(simulate_failure=mode)
        elif adapter == "flashloan":
            FlashloanAdapter(
                "http://bad", alt_api_urls=["http://alt"], ops_agent=ops
            ).trigger("ETH", 1, simulate_failure=mode)
    except Exception as exc:
        LOGGER.log("chaos_error", adapter=adapter, risk_level="high", error=str(exc))
        _update_metrics(adapter)
        ops.notify(json.dumps({"adapter": adapter, "failure": mode, "error": str(exc)}))
        os.environ["OPS_CRITICAL_EVENT"] = "1"
        log_mutation("adapter_chaos", adapter=adapter, failure=mode, fallback=False)
    else:
        LOGGER.log("chaos_ok", adapter=adapter, mode=mode, risk_level="low")
        log_mutation("adapter_chaos", adapter=adapter, failure=mode, fallback=True)


# ---------------------------------------------------------------------------

def run_once() -> None:
    ops = OpsAgent({})
    adapters = os.getenv("CHAOS_ADAPTERS", "dex,bridge,cex,flashloan").split(",")
    modes = os.getenv("CHAOS_MODES", "network,rpc,downtime,data_poison").split(",")
    _inject(random.choice(adapters), random.choice(modes), ops)


# ---------------------------------------------------------------------------

def run_scheduler() -> None:
    interval = int(os.getenv("CHAOS_INTERVAL", "3600"))
    while True:
        run_once()
        time.sleep(interval)


if __name__ == "__main__":  # pragma: no cover - CLI entry
    import argparse

    parser = argparse.ArgumentParser(description="Run scheduled chaos injections")
    parser.add_argument("--once", action="store_true", help="Run a single injection and exit")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_scheduler()
