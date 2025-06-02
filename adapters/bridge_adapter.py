"""Token bridge API adapter."""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger("bridge_adapter")


class BridgeAdapter:
    """Handle token bridging via a third-party API."""

    def __init__(
        self,
        api_url: str,
        *,
        alt_api_url: str | None = None,
        alt_api_urls: List[str] | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        alts = []
        if alt_api_urls:
            alts.extend(alt_api_urls)
        if alt_api_url:
            alts.append(alt_api_url)
        self.alt_api_urls = [a.rstrip("/") for a in alts]
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"bridge_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    # ------------------------------------------------------------------
    def bridge(
        self, from_chain: str, to_chain: str, token: str, amount: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        if kill_switch_triggered():
            record_kill_event("bridge_adapter.bridge")
            raise RuntimeError("Kill switch active")
        data = {"from": from_chain, "to": to_chain, "token": token, "amount": amount}
        try:
            import requests  # type: ignore[import-untyped]

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"bridge": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(f"{self.api_url}/bridge", json=data, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("bridge_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.post(f"{alt}/bridge", json=data, timeout=5)
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="bridge_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="bridge_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise


