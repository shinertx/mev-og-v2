"""Flashloan execution adapter."""

from __future__ import annotations

import json
import os
import random
from typing import Any, Dict, Optional

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
        alt_api_urls: list[str] | None = None,
        ops_agent: OpsAgent | None = None,
        fail_threshold: int = 3,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        urls = list(alt_api_urls or [])
        if alt_api_url:
            urls.append(alt_api_url)
        self.alt_api_urls = [u.rstrip("/") for u in urls]
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOG.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(
                json.dumps({"adapter": "flashloan", "event": event, "error": str(err)})
            )
        log_mutation("adapter_chaos", adapter="flashloan", failure=event, fallback=False)
        if self.failures >= self.fail_threshold:
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            raise RuntimeError("circuit breaker open")

    def trigger(
        self, token: str, amount: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        """Perform the flashloan using an external service."""
        try:
            import requests  # type: ignore

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
            for url in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    resp = requests.post(
                        f"{url}/flashloan",
                        json={"token": token, "amount": amount},
                        timeout=5,
                    )
                    resp.raise_for_status()
                    LOG.log("fallback_success", risk_level="low", alt=url)
                    log_mutation(
                        "adapter_chaos", adapter="flashloan", failure="flashloan_fail", fallback=url
                    )
                    self.failures = 0
                    return resp.json()
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            raise
