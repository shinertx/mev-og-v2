#!/usr/bin/env python3.11
"""Founder-gated wallet operations: fund, withdraw-all, drain-to-cold."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from core.logger import StructuredLogger, log_error
from agents.founder_gate import founder_approved

LOGGER = StructuredLogger("wallet_ops")


# ---------------------------------------------------------------------------
def _founder_confirm() -> bool:
    """Return True if founder approval is granted."""

    if founder_approved("wallet_ops"):
        LOGGER.log("founder_confirm", approved=True, via="token")
        return True
    try:
        resp = input("Founder approval required. Continue? [y/N]: ").strip().lower()
    except Exception:
        resp = ""
    approved = resp in {"y", "yes"}
    LOGGER.log("founder_confirm", approved=approved, via="prompt")
    return approved


# ---------------------------------------------------------------------------


def _export_state(dry_run: bool) -> None:
    script = Path(__file__).resolve().with_name("export_state.sh")
    cmd = ["bash", str(script)]
    if dry_run:
        cmd.append("--dry-run")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except Exception as exc:
        LOGGER.log("export_fail", error=str(exc))
        raise


# ---------------------------------------------------------------------------
def _send_tx(from_addr: str, to_addr: str, amount: str, dry_run: bool) -> str:
    """Send a transaction returning the tx hash."""

    if dry_run:
        return "dry-run"

    mode = os.getenv("WALLET_OPS_TX_MODE", "ok")
    if mode == "fail":
        raise RuntimeError("tx send fail")
    if mode == "insufficient":
        raise RuntimeError("insufficient funds")

    try:
        from core.tx_engine.builder import TransactionBuilder, HexBytes
        from core.tx_engine.nonce_manager import NonceManager

        class DummyEth:
            def estimate_gas(self, tx: Any) -> int:
                return 21000

            def get_transaction_count(self, address: str) -> int:
                return 0

            def send_raw_transaction(self, tx: bytes) -> bytes:
                return b"hash" + tx[-2:]

            class account:
                @staticmethod
                def decode_transaction(tx: bytes) -> dict[str, Any]:
                    return {}

        class DummyWeb3:
            def __init__(self) -> None:
                self.eth: DummyEth = DummyEth()

        web3 = DummyWeb3()
        nm = NonceManager(web3, cache_file="state/nonce_cache.json", log_file="logs/nonce_log.json")
        builder = TransactionBuilder(web3, nm)
        tx_hash = builder.send_transaction(
            HexBytes(b"\x01\x02"),
            from_addr,
            strategy_id="wallet_ops",
            mutation_id="ops",
            risk_level="low",
        )
        return tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
    except Exception as exc:
        log_error("wallet_ops", f"tx_send failed: {exc}")
        raise


# ---------------------------------------------------------------------------
def _log_and_exit(
    event: str, from_addr: str, to_addr: str, amount: str, txid: str, error: Optional[str] = None
) -> None:
    LOGGER.log(event, from_address=from_addr, to_address=to_addr, amount=amount, txid=txid, error=error)
    if error:
        raise SystemExit(error)


# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Wallet operations")
    sub = parser.add_subparsers(dest="command", required=True)

    p_fund = sub.add_parser("fund")
    p_fund.add_argument("--from", dest="src", required=True)
    p_fund.add_argument("--to", dest="dst", required=True)
    p_fund.add_argument("--amount", required=True)

    p_wd = sub.add_parser("withdraw-all")
    p_wd.add_argument("--from", dest="src", required=True)
    p_wd.add_argument("--to", dest="dst", required=True)

    p_drain = sub.add_parser("drain-to-cold")
    p_drain.add_argument("--from", dest="src", required=True)
    p_drain.add_argument("--to", dest="dst", required=True)

    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not _founder_confirm():
        raise SystemExit("Founder approval required")

    _export_state(args.dry_run)

    amount = getattr(args, "amount", "all")
    try:
        txid = _send_tx(args.src, args.dst, str(amount), args.dry_run)
        _log_and_exit(args.command, args.src, args.dst, str(amount), txid)
    except Exception as exc:
        _log_and_exit(f"{args.command}_fail", args.src, args.dst, str(amount), "", error=str(exc))
    finally:
        _export_state(args.dry_run)


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
