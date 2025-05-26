"""Uniswap V3 price feed across Ethereum, Arbitrum, and Optimism.

Module purpose and system role:
    - Provide current pool price data for cross-domain strategies.
    - Supports L1 and major L2 networks with env-configured RPC endpoints.

Integration points and dependencies:
    - Uses `web3` for RPC calls.
    - Relies on minimal UniswapV3Pool ABI to read `slot0` and token decimals.

Simulation/test hooks and kill conditions:
    - Designed to operate against forked RPC nodes.
    - Methods raise if required data is missing to prevent false prices.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
import logging
import time
from typing import Any, Dict

from core.logger import log_error

# Warn if block age exceeds this threshold (seconds)
PRICE_FRESHNESS_SEC = int(os.getenv("PRICE_FRESHNESS_SEC", "30"))

try:  # pragma: no cover - optional dependency
    from web3 import Web3
    from web3.contract import Contract
except Exception:  # pragma: no cover - only when web3 missing
    Web3 = None  # type: ignore
    Contract = Any  # type: ignore

UNISWAP_V3_POOL_ABI = [
    {
        "inputs": [],
        "name": "slot0",
        "outputs": [
            {"internalType": "uint160", "name": "sqrtPriceX96", "type": "uint160"},
            {"internalType": "int24", "name": "tick", "type": "int24"},
            {"internalType": "uint16", "name": "observationIndex", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinality", "type": "uint16"},
            {"internalType": "uint16", "name": "observationCardinalityNext", "type": "uint16"},
            {"internalType": "uint8", "name": "feeProtocol", "type": "uint8"},
            {"internalType": "bool", "name": "unlocked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token0",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "token1",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


@dataclass
class PriceData:
    """Structured price information for audit and mutation."""

    price: float
    pool: str
    block: int
    timestamp: int
    block_age: int


class UniswapV3Feed:
    """Fetch price from Uniswap V3 pools across multiple domains."""

    def __init__(self, rpc_urls: Dict[str, str] | None = None) -> None:
        if rpc_urls is None:
            rpc_urls = {
                "ethereum": os.getenv("RPC_ETHEREUM_URL", "http://localhost:8545"),
                "arbitrum": os.getenv("RPC_ARBITRUM_URL", "http://localhost:8545"),
                "optimism": os.getenv("RPC_OPTIMISM_URL", "http://localhost:8545"),
            }
        self.rpc_urls = rpc_urls
        self.web3s: Dict[str, Web3] = {}
        if Web3 is not None:  # pragma: no cover - environment dependent
            for domain, url in rpc_urls.items():
                self.web3s[domain] = Web3(Web3.HTTPProvider(url))

    def _get_web3(self, domain: str) -> Web3:
        if Web3 is None:  # pragma: no cover - web3 not installed
            raise RuntimeError("web3 package required")
        if domain not in self.web3s:
            raise ValueError(f"Unknown domain {domain}")
        return self.web3s[domain]

    def _get_token_decimals(self, w3: Web3, token_address: str) -> int:
        erc20_abi = [{"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"}]
        token = w3.eth.contract(address=token_address, abi=erc20_abi)
        return int(token.functions.decimals().call())

    def fetch_price(self, pool: str, domain: str) -> PriceData:
        """Return price for ``pool`` on ``domain``."""
        w3 = self._get_web3(domain)
        try:
            contract: Contract = w3.eth.contract(address=pool, abi=UNISWAP_V3_POOL_ABI)
            slot0 = contract.functions.slot0().call()
            sqrt_price_x96 = slot0[0]
            token0 = contract.functions.token0().call()
            token1 = contract.functions.token1().call()
            dec0 = self._get_token_decimals(w3, token0)
            dec1 = self._get_token_decimals(w3, token1)
            price = (sqrt_price_x96 ** 2) / (2 ** 192)
            price *= 10 ** (dec0 - dec1)
            block = w3.eth.get_block("latest")
        except Exception as exc:
            log_error("UniswapV3Feed", str(exc), event="fetch_price", pool=pool, domain=domain)
            raise
        block_age = int(time.time()) - block.timestamp
        if block_age > PRICE_FRESHNESS_SEC:
            logging.warning("stale price data: %s sec old on %s", block_age, domain)
            log_error(
                "UniswapV3Feed",
                "stale price",
                event="stale_price",
                pool=pool,
                domain=domain,
                block_age=block_age,
            )
        return PriceData(price=float(price), pool=pool, block=block.number, timestamp=block.timestamp, block_age=block_age)
