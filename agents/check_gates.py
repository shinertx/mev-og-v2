"""CLI helper to verify all agent gates are green."""

from agents.capital_lock import CapitalLock
from agents.ops_agent import OpsAgent
from agents.drp_agent import DRPAgent
from agents.gatekeeper import gates_green
from agents.agent_registry import get_value


def main() -> None:
    lock = CapitalLock(0, 0, 0)
    lock.blocked = bool(get_value("capital_locked", False))
    ops = OpsAgent({})
    ops.paused = bool(get_value("paused", False))
    drp = DRPAgent()
    drp.ready = bool(get_value("drp_ready", True))
    if not gates_green(lock, ops, drp):
        raise SystemExit("agent gates not green")


if __name__ == "__main__":  # pragma: no cover - CLI
    main()
