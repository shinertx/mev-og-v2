#!/bin/bash

# Run the fork simulation harness for a given strategy.
# Usage: scripts/simulate_fork.sh [--target=strategies/<module>] [--strategy=<name>]
#        scripts/simulate_fork.sh <name>

set -euo pipefail

TARGET=""
STRATEGY=""

for arg in "$@"; do
    case $arg in
        --target=*)
            TARGET="${arg#*=}"
            shift
            ;;
        --strategy=*)
            STRATEGY="${arg#*=}"
            shift
            ;;
        *)
            if [[ -z "$TARGET" && -z "$STRATEGY" ]]; then
                STRATEGY="$arg"
            else
                echo "Usage: $0 [--target=strategies/<module>] [--strategy=<name>]" >&2
                exit 1
            fi
            ;;
    esac
done

if [[ -n "$STRATEGY" ]]; then
    NAME="$STRATEGY"
elif [[ -n "$TARGET" ]]; then
    NAME="$(basename "$TARGET")"
else
    NAME="cross_domain_arb"
fi
if [[ "$NAME" == "cross_domain_arb" ]]; then
    NAME="cross_arb"
elif [[ "$NAME" == "cross_rollup_superbot" ]]; then
    NAME="cross_rollup_superbot"
elif [[ "$NAME" == "l3_app_rollup_mev" ]]; then
    NAME="l3_app_rollup_mev"
elif [[ "$NAME" == "l3_sequencer_mev" ]]; then
    NAME="l3_sequencer_mev"
elif [[ "$NAME" == "nft_liquidation" ]]; then
    NAME="nft_liquidation"
elif [[ "$NAME" == "rwa_settlement" ]]; then
    NAME="rwa_settlement"
fi
SCRIPT="infra/sim_harness/fork_sim_${NAME}.py"

if [[ ! -f "$SCRIPT" ]]; then
    echo "Unknown strategy: $NAME" >&2
    exit 1
fi

PYTHON=${PYTHON:-python}
"$PYTHON" "$SCRIPT"

