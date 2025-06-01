"""Flashloan execution adapter."""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger
from ai.mutation_log import log_mutation

LOG = StructuredLogger("flashloan_adapter")


class FlashloanAdapter:
    """Execute flashloans to induce price moves for latency farming."""

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
        LOG.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"flashloan_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            raise RuntimeError("circuit breaker open")

    def trigger(
        self, token: str, amount: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        """Perform the flashloan using an external service."""
        try:
            import requests  # type: ignore[import-untyped]

            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                return {"flashloan": "bad"}
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = requests.post(
                f"{self.api_url}/flashloan",
                json={"token": token, "amount": amount},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("flashloan_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOG.log("fallback_try", risk_level="low", alt=alt)
                    resp = requests.post(
                        f"{alt}/flashloan",
                        json={"token": token, "amount": amount},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    LOG.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="flashloan_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="flashloan_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise
