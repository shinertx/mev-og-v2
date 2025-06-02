"""Discover new DEX pools across domains."""

from __future__ import annotations

from dataclasses import dataclass
import os
import random
from typing import List, Dict, Any

import requests

from agents.ops_agent import OpsAgent

from core.logger import StructuredLogger
from core.tx_engine.kill_switch import kill_switch_triggered, record_kill_event
from ai.mutation_log import log_mutation

LOG = StructuredLogger("pool_scanner")


@dataclass
class PoolInfo:
    pool: str
    domain: str


class PoolScanner:
    """Scan subgraph or RPC endpoints for newly deployed pools."""

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
        self.session = requests.Session()

    def _validate_pools(self, data: List[Dict[str, Any]]) -> List[PoolInfo]:
        pools = []
        for item in data:
            pool = item.get("pool")
            domain = item.get("domain")
            if isinstance(pool, str) and isinstance(domain, str):
                pools.append(PoolInfo(pool=pool, domain=domain))
            else:
                raise ValueError("invalid pool data")
        return pools

    def _alert(self, event: str, err: Exception) -> None:
        self.failures += 1
        LOG.log(event, risk_level="high", error=str(err))
        if self.ops_agent:
            self.ops_agent.notify(f"pool_scanner:{event}:{err}")
        if self.failures >= self.fail_threshold:
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            raise RuntimeError("circuit breaker open")

    def scan(self, *, simulate_failure: str | None = None) -> List[PoolInfo]:
        if kill_switch_triggered():
            record_kill_event("pool_scanner.scan")
            return []
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                bad = [PoolInfo(pool="bad", domain="bad")]
                self._validate_pools([{"pool": b.pool, "domain": b.domain} for b in bad])
                return bad
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = self.session.get(f"{self.api_url}/pools", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return self._validate_pools(data)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("scan_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOG.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.get(f"{alt}/pools", timeout=5)
                    resp.raise_for_status()
                    LOG.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    data = resp.json()
                    log_mutation(
                        "adapter_chaos",
                        adapter="pool_scanner",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return self._validate_pools(data)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="pool_scanner",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            return []

    def scan_l3(self, *, simulate_failure: str | None = None) -> List[PoolInfo]:
        """Discover L3/app rollup pools."""
        if kill_switch_triggered():
            record_kill_event("pool_scanner.scan_l3")
            return []
        try:
            if simulate_failure == "network":
                raise RuntimeError("sim net")
            if simulate_failure == "rpc":
                raise ValueError("sim rpc")
            if simulate_failure == "data_poison":
                bad = [PoolInfo(pool="bad", domain="l3")]
                self._validate_pools([{"pool": b.pool, "domain": b.domain} for b in bad])
                return bad
            if simulate_failure == "downtime":
                raise RuntimeError("sim 503")

            resp = self.session.get(f"{self.api_url}/l3_pools", timeout=5)
            resp.raise_for_status()
            data = resp.json()
            return self._validate_pools(data)
        except Exception as exc:  # pragma: no cover - network errors
            self._alert("scan_l3_fail", exc)
            for alt in random.sample(self.alt_api_urls, len(self.alt_api_urls)):
                try:
                    LOG.log("fallback_try", risk_level="low", alt=alt)
                    resp = self.session.get(f"{alt}/l3_pools", timeout=5)
                    resp.raise_for_status()
                    LOG.log("fallback_success", risk_level="low", alt=alt)
                    self.failures = 0
                    data = resp.json()
                    log_mutation(
                        "adapter_chaos",
                        adapter="pool_scanner",
                        failure=simulate_failure or "runtime",
                        fallback="success",
                    )
                    return self._validate_pools(data)
                except Exception as exc2:  # pragma: no cover - network errors
                    self._alert("fallback_fail", exc2)
            os.environ["OPS_CRITICAL_EVENT"] = "1"
            log_mutation(
                "adapter_chaos",
                adapter="pool_scanner",
                failure=simulate_failure or "runtime",
                fallback="fail",
            )
            return []
