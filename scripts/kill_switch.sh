#!/bin/bash

# Manual kill switch trigger script
# Purpose: allow operators or DRP to enable/disable the system kill switch.
# Logs all actions to logs/kill_log.json in JSON format for audit.

set -euo pipefail

MODE="trigger"
DRY=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY=1
            shift
            ;;
        --clean)
            MODE="clean"
            shift
            ;;
        *)
            echo "Usage: $0 [--dry-run] [--clean]" >&2
            exit 1
            ;;
    esac
done

FLAG_FILE="${KILL_SWITCH_FLAG_FILE:-./flags/kill_switch.txt}"
LOG_FILE="${KILL_SWITCH_LOG_FILE:-logs/kill_log.json}"
USER_NAME="$(whoami 2>/dev/null || echo unknown)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TRACE_ID="${TRACE_ID:-}"

log_event() {
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '{"timestamp":"%s","mode":"%s","user":"%s","flag_file":"%s","trace_id":"%s"}\n' \
        "$TIMESTAMP" "$1" "$USER_NAME" "$FLAG_FILE" "$TRACE_ID" >> "$LOG_FILE"
}

if [[ $DRY -eq 1 ]]; then
    echo "DRY RUN: would ${MODE} kill switch"
    log_event "dry-run"
    exit 0
fi

if [[ $MODE == "clean" ]]; then
    rm -f "$FLAG_FILE"
    unset KILL_SWITCH
    echo "Kill switch cleaned"
    log_event "clean"
    exit 0
fi

# Trigger mode
mkdir -p "$(dirname "$FLAG_FILE")"
echo "$TIMESTAMP $USER_NAME" > "$FLAG_FILE"

export KILL_SWITCH=1

echo "Kill switch ACTIVATED"
log_event "trigger"
