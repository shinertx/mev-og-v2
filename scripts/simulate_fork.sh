#!/bin/bash

# Run the fork simulation harness for a given strategy.
# Usage: scripts/simulate_fork.sh --target=strategies/<module>

set -euo pipefail

TARGET="strategies/cross_domain_arb"

for arg in "$@"; do
    case $arg in
        --target=*)
            TARGET="${arg#*=}"
            shift
            ;;
        *)
            echo "Usage: $0 --target=strategies/<module>" >&2
            exit 1
            ;;
    esac
done

NAME="$(basename "$TARGET")"
if [[ "$NAME" == "cross_domain_arb" ]]; then
    NAME="cross_arb"
elif [[ "$NAME" == "l3_sequencer_mev" ]]; then
    NAME="l3_sequencer_mev"
elif [[ "$NAME" == "nft_liquidation" ]]; then
    NAME="nft_liquidation"
elif [[ "$NAME" == "rwa_settlement" ]]; then
    NAME="rwa_settlement"
fi
SCRIPT="infra/sim_harness/fork_sim_${NAME}.py"

if [[ ! -f "$SCRIPT" ]]; then
    echo "Unknown target: $TARGET" >&2
    exit 1
fi

PYTHON=${PYTHON:-python}
"$PYTHON" "$SCRIPT"

