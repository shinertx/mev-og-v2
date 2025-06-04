"""Adapters package for external APIs."""

# Lazy imports to avoid optional dependency issues at package import time.
from typing import Any

BridgeAdapter: Any = None
CEXAdapter: Any = None
DEXAdapter: Any = None
FlashloanAdapter: Any = None
PoolScanner: Any = None
PoolInfo: Any = None
DuneAnalyticsAdapter: Any = None
WhaleAlertAdapter: Any = None
CoinbaseWebSocketAdapter: Any = None

__all__ = [
    "BridgeAdapter",
    "CEXAdapter",
    "DEXAdapter",
    "FlashloanAdapter",
    "PoolScanner",
    "PoolInfo",
    "DuneAnalyticsAdapter",
    "WhaleAlertAdapter",
    "CoinbaseWebSocketAdapter",
]
