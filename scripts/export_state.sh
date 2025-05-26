#!/bin/bash

# Export logs and state for disaster recovery.

set -euo pipefail

MODE="export"
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

EXPORT_DIR="${EXPORT_DIR:-export}"
LOG_FILE="${EXPORT_LOG_FILE:-logs/export_state.json}"
USER_NAME="$(whoami 2>/dev/null || echo unknown)"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ARCHIVE="drp_export_${TIMESTAMP//:/-}.tar.gz"

log_event() {
    mkdir -p "$(dirname "$LOG_FILE")"
    printf '{"timestamp":"%s","mode":"%s","user":"%s","archive":"%s"}\n' "$TIMESTAMP" "$1" "$USER_NAME" "$EXPORT_DIR/$ARCHIVE" >> "$LOG_FILE"
}

if [[ $DRY -eq 1 ]]; then
    echo "DRY RUN: would ${MODE} state"
    log_event "dry-run"
    exit 0
fi

mkdir -p "$EXPORT_DIR"

if [[ $MODE == "clean" ]]; then
    rm -rf logs/* state/*
    echo "State cleaned"
    log_event "clean"
    exit 0
fi

# export mode
ITEMS=()
for d in logs state active keys; do
    if [[ -e "$d" ]]; then
        ITEMS+=("$d")
    fi
done
if [[ ${#ITEMS[@]} -gt 0 ]]; then
    tar -czf "$EXPORT_DIR/$ARCHIVE" "${ITEMS[@]}"
    echo "Export created at $EXPORT_DIR/$ARCHIVE"
else
    echo "Warning: nothing to export" >&2
fi

log_event "export"
