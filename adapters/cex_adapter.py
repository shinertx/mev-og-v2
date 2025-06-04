"""Simple CEX adapter supporting order placement and balance check."""

from __future__ import annotations

import os
import random
from typing import Any, Dict, List
import math

import requests

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger

try:  # optional kill switch for tests
    from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
except Exception:  # pragma: no cover - optional dependency
    kill_switch_triggered = None  # type: ignore[assignment]
    record_kill_event = None  # type: ignore[assignment]
from ai.mutation_log import log_mutation

LOGGER = StructuredLogger("cex_adapter")


class CEXAdapter:
    """HTTP-based adapter for a centralized exchange."""

    def __init__(
        self,
        api_url: str,
        api_key: str,
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
        self.api_key = api_key
        self.ops_agent = ops_agent
        self.fail_threshold = fail_threshold
        self.failures = 0
        self.session = requests.Session()

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOGGER.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"cex_adapter:{event}:{err}")
        if self.failures >= self.fail_threshold:
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            raise RuntimeError("circuit breaker open")

    # ------------------------------------------------------------------
    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def _validate_balance(self, data: Dict[str, Any]) -> Dict[str, Any]:
        bal = data.get("balance")
        if bal is not None:
            try:
                val = float(bal)
            except Exception as exc:
                raise ValueError("invalid balance") from exc
            if not math.isfinite(val):
                raise ValueError("invalid balance")
            return {"balance": val}
        if "ok" in data:
            if isinstance(data.get("ok"), bool):
                return {"ok": data["ok"]}
        raise ValueError("missing balance")

    def _validate_order(self, data: Dict[str, Any]) -> Dict[str, Any]:
        if "order" in data:
            if isinstance(data["order"], str):
                return {"order": data["order"]}
            raise ValueError("invalid order")
        if "ok" in data:
            if isinstance(data.get("ok"), bool):
                return {"ok": data["ok"]}
        raise ValueError("missing order")

    # ------------------------------------------------------------------
    def get_balance(self, *, simulate_failure: str | None = None) -> Dict[str, Any]:
        if kill_switch_triggered and kill_switch_triggered():
            if record_kill_event:
                record_kill_event("cex_adapter.get_balance")
            raise RuntimeError("Kill switch active")
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                data: Dict[str, Any] = {"balance": "bad"}
                self._validate_balance(data)
                return data
            if simulate_failure == "downtime":
                raise RuntimeError("sim 429")

            resp = self.session.get(
                f"{self.api_url}/balance", headers=self._headers(), timeout=5
            )
            resp.raise_for_status()
            data = resp.json()
            return self._validate_balance(data)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("balance_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.get(
                        f"{alt}/balance", headers=self._headers(), timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="cex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    data = resp.json()
                    return self._validate_balance(data)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="cex_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise

    # ------------------------------------------------------------------
    def place_order(
        self, side: str, size: float, price: float, *, simulate_failure: str | None = None
    ) -> Dict[str, Any]:
        data = {"side": side, "size": size, "price": price}
        if kill_switch_triggered and kill_switch_triggered():
            if record_kill_event:
                record_kill_event("cex_adapter.place_order")
            raise RuntimeError("Kill switch active")
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                od: Dict[str, Any] = {"order": "bad"}
                self._validate_order(od)
                return od
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = self.session.post(
                f"{self.api_url}/order", json=data, headers=self._headers(), timeout=5
            )
            resp.raise_for_status()
            res = resp.json()
            return self._validate_order(res)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("order_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOGGER.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.post(
                        f"{alt}/order", json=data, headers=self._headers(), timeout=5
                    )
                    resp.raise_for_status()
                    LOGGER.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    log_mutation(
                        "adapter_chaos",
                        adapter="cex_adapter",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    ret = resp.json()
                    return self._validate_order(ret)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="cex_adapter",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            raise

