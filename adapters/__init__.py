"""Adapters package for external APIs."""

# Lazy imports to avoid optional dependency issues at package import time.
BridgeAdapter = None
CEXAdapter = None
DEXAdapter = None
FlashloanAdapter = None
PoolScanner = None
PoolInfo = None
DuneAnalyticsAdapter = None
WhaleAlertAdapter = None
CoinbaseWebSocketAdapter = None

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
