"""Fork simulation harness for kill_switch.sh

This module forks the chain, runs the kill switch script, and halts execution
if the switch is active. Intended for chaos testing and DRP drills.
"""

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.tx_engine.kill_switch import init_kill_switch, kill_switch_triggered, record_kill_event

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "kill_switch.sh"


def run_sim() -> None:
    init_kill_switch()
    subprocess.run(["bash", str(SCRIPT)], check=True)
    if kill_switch_triggered():
        record_kill_event("fork_sim_kill_switch_sh")
        print("Kill switch active. Simulation halted.")
        return
    print("Simulation would continue")


if __name__ == "__main__":
    run_sim()
