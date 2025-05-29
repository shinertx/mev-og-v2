"""Adapters package for external APIs."""

from .bridge_adapter import BridgeAdapter
from .cex_adapter import CEXAdapter
from .dex_adapter import DEXAdapter
from .flashloan_adapter import FlashloanAdapter
from .pool_scanner import PoolScanner, PoolInfo
from .alpha_signals import DuneAnalyticsAdapter, WhaleAlertAdapter, CoinbaseWebSocketAdapter

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
