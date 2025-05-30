"""Simulates forked mainnet kill switch testing for MEV-OG."""



from core.tx_engine.kill_switch import (
    init_kill_switch,
    kill_switch_triggered,
    record_kill_event,
    flag_file,
)


def run_sim() -> None:
    init_kill_switch()
    print("Starting fork sim...")
    if kill_switch_triggered():
        record_kill_event("fork_sim_start")
        print("Kill switch active. Exiting.")
        return
    print("Sending transaction 1")
    # Activate kill switch during operation
    ff = flag_file()
    ff.parent.mkdir(parents=True, exist_ok=True)
    ff.write_text("1")
    if kill_switch_triggered():
        record_kill_event("fork_sim_tx")
        print("Kill switch triggered during tx. Halting.")
        return
    print("Simulation completed")


if __name__ == "__main__":
    run_sim()
