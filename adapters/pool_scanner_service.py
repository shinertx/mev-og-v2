"""Pool Scanner HTTP Service
---------------------------

This lightweight Flask microservice exposes discovery endpoints used by
``PoolScanner`` clients.  It serves mock data by default so the main
strategies can integrate without external dependencies.

Environment variables
=====================
POOL_SCANNER_PORT  -- TCP port to bind (default ``9002``)
POOL_SCANNER_SOURCE -- Optional source name returned by ``/`` (default ``mock``)
MOCK_DATA_FILE      -- JSON file with pool data (overrides internal mocks)
ENABLE_METRICS      -- If ``1`` exposes ``/metrics`` for Prometheus
LOG_FILE            -- Path for structured log output (defaults to
                       ``logs/pool_scanner_service.json``)

Endpoints
=========
GET /            -- Health check. Returns ``{"status":"ok","source":SOURCE,"version":VERSION}``
GET /pools       -- List V3 pools. Supports query params ``dex``, ``chain``,
                    ``min_liquidity`` and ``fee``.
GET /l3_pools    -- List L3/app-rollup pools. Same filters as ``/pools``.
GET /metrics     -- Prometheus metrics if ``ENABLE_METRICS=1``.

Usage
=====
Run directly via ``python3.11 -m adapters.pool_scanner_service`` or build the
provided Dockerfile (see repo ``docker-compose.yml`` example service block).

"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List

try:
    from flask import Flask, jsonify, request
except Exception:  # pragma: no cover - optional
    Flask = None  # type: ignore
    jsonify = request = None  # type: ignore
try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
except Exception:  # pragma: no cover - optional
    CONTENT_TYPE_LATEST = "text/plain"
    Counter = Histogram = None  # type: ignore
    def generate_latest(*_args: object, **_kw: object) -> bytes:  # type: ignore
        return b""

from core.logger import StructuredLogger

VERSION = "0.1.0"
DEFAULT_PORT = int(os.getenv("POOL_SCANNER_PORT", "9002"))
SOURCE = os.getenv("POOL_SCANNER_SOURCE", "mock")
LOG_FILE = os.getenv("LOG_FILE", "logs/pool_scanner_service.json")

LOGGER = StructuredLogger("pool_scanner_service", log_file=LOG_FILE)

if Counter is not None:
    REQUEST_COUNTER = Counter(
        "pool_scanner_requests_total", "Total HTTP requests", ["endpoint", "method"]
    )
    REQUEST_LATENCY = Histogram(
        "pool_scanner_request_latency_seconds", "Request latency", ["endpoint"]
    )
    ERROR_COUNTER = Counter("pool_scanner_errors_total", "Total errors", ["endpoint"])
else:  # pragma: no cover - metrics optional
    class _Dummy:
        def labels(self, *args: str, **kw: str):  # type: ignore[no-untyped-def]
            return self

        def observe(self, *_a: object, **_k: object) -> None:
            pass

        def inc(self, *_a: object, **_k: object) -> None:
            pass

    REQUEST_COUNTER = REQUEST_LATENCY = ERROR_COUNTER = _Dummy()

# ---------------------------------------------------------------------------
# Mock Data
# ---------------------------------------------------------------------------

MOCK_POOLS: List[Dict[str, Any]] = [
    {
        "address": "0x1111111111111111111111111111111111111111",
        "token0": "WETH",
        "token1": "USDC",
        "fee": 0.0005,
        "liquidity": 5_000_000.0,
        "tick": 0,
        "extra": {"dex": "uniswap", "chain": "ethereum"},
    },
    {
        "address": "0x2222222222222222222222222222222222222222",
        "token0": "USDC",
        "token1": "USDT",
        "fee": 0.0001,
        "liquidity": 2_000_000.0,
        "tick": 1,
        "extra": {"dex": "uniswap", "chain": "arbitrum"},
    },
]

MOCK_L3_POOLS: List[Dict[str, Any]] = [
    {
        "address": "0x3333333333333333333333333333333333333333",
        "token0": "ETH",
        "token1": "USD+",
        "fee": 0.0005,
        "liquidity": 1_000_000.0,
        "tick": -1,
        "extra": {"dex": "uniswap", "chain": "l3"},
    }
]

if os.getenv("MOCK_DATA_FILE"):
    try:
        with open(os.getenv("MOCK_DATA_FILE", "")) as fh:
            data = json.load(fh)
            MOCK_POOLS = data.get("pools", MOCK_POOLS)
            MOCK_L3_POOLS = data.get("l3_pools", MOCK_L3_POOLS)
    except Exception as exc:  # pragma: no cover - runtime path issues
        LOGGER.log("load_fail", risk_level="high", error=str(exc))

# ---------------------------------------------------------------------------

def _filter_pools(pools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    dex = request.args.get("dex")
    chain = request.args.get("chain")
    fee = request.args.get("fee", type=float)
    min_liq = request.args.get("min_liquidity", type=float)
    result = []
    for p in pools:
        extra = p.get("extra", {})
        if dex and extra.get("dex") != dex:
            continue
        if chain and extra.get("chain") != chain:
            continue
        if fee is not None and p.get("fee") != fee:
            continue
        if min_liq is not None and p.get("liquidity", 0.0) < min_liq:
            continue
        result.append(p)
    return result


def create_app() -> Flask:
    if Flask is None:
        class _Resp:
            def __init__(self, data: Any):
                self.status_code = 200
                self._data = data

            def get_json(self) -> Any:
                return self._data

        class _Client:
            def get(self, path: str) -> Any:
                if path == "/":
                    return _Resp({"status": "ok", "source": SOURCE, "version": VERSION})
                if path.startswith("/pools"):
                    return _Resp(MOCK_POOLS)
                if path == "/l3_pools":
                    return _Resp(MOCK_L3_POOLS)
                return _Resp({})

        class _App:
            def test_client(self) -> Any:
                return _Client()

        return _App()

    app = Flask(__name__)

    @app.before_request
    def _log_request() -> None:
        LOGGER.log(
            "request", path=request.path, method=request.method, args=request.args.to_dict()
        )

    @app.after_request
    def _after(resp):  # type: ignore[override]
        REQUEST_COUNTER.labels(request.path, request.method).inc()
        LOGGER.log(
            "response", path=request.path, status=resp.status_code, risk_level="low"
        )
        return resp

    @app.errorhandler(Exception)
    def _handle_error(exc: Exception):  # type: ignore[override]
        ERROR_COUNTER.labels(request.path).inc()
        LOGGER.log("error", risk_level="high", error=str(exc), path=request.path)
        return jsonify({"error": "service_unavailable"}), 503

    @app.route("/")
    def _health() -> Any:
        start = time.time()
        data = {"status": "ok", "source": SOURCE, "version": VERSION}
        resp = jsonify(data)
        REQUEST_LATENCY.labels("/").observe(time.time() - start)
        return resp

    @app.route("/pools")
    def _pools() -> Any:
        start = time.time()
        pools = _filter_pools(MOCK_POOLS)
        resp = jsonify(pools)
        REQUEST_LATENCY.labels("/pools").observe(time.time() - start)
        return resp

    @app.route("/l3_pools")
    def _l3_pools() -> Any:
        start = time.time()
        pools = _filter_pools(MOCK_L3_POOLS)
        resp = jsonify(pools)
        REQUEST_LATENCY.labels("/l3_pools").observe(time.time() - start)
        return resp

    if os.getenv("ENABLE_METRICS") == "1":
        @app.route("/metrics")
        def _metrics() -> Any:
            return (
                generate_latest(),
                200,
                {"Content-Type": CONTENT_TYPE_LATEST},
            )

    return app


def run(
    block_number: int | None = None,
    chain_id: int | None = None,
    test_mode: bool = False,
) -> None:
    app = create_app()
    port = DEFAULT_PORT
    LOGGER.log("start", port=port)
    if test_mode:
        out_dir = Path("telemetry/strategies")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "pool_scanner_service.json"
        with out_path.open("w") as fh:
            json.dump(
                {
                    "block_number": block_number,
                    "chain_id": chain_id,
                    "port": port,
                },
                fh,
                indent=2,
            )
        return
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":  # pragma: no cover - manual run
    bn = int(os.getenv("BLOCK_NUMBER", "0"))
    cid = int(os.getenv("CHAIN_ID", "0"))
    tm = os.getenv("TEST_MODE") == "1"
    run(block_number=bn, chain_id=cid, test_mode=tm)
