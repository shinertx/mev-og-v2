#!/bin/bash

# Export a full project snapshot for audits.
# Includes git metadata, strategy TTL info, patch diffs, secrets config,
# simulation results, and capital gate metrics.

set -euo pipefail

DRY=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)
            DRY=1
            shift
            ;;
        *)
            echo "Usage: $0 [--dry-run]" >&2
            exit 1
            ;;
    esac
done

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
EXPORT_DIR="${EXPORT_DIR:-/export}"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
ARCHIVE="drp_export_FULL_${TIMESTAMP//:/-}.tar.gz"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT


# --- meta info ---
SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
AUDIT_SHA="$(git -C "$ROOT" log --grep='founder audit' -n1 --pretty=%H 2>/dev/null || true)"
printf '{"timestamp":"%s","sha":"%s","audit_sha":"%s"}\n' "$TIMESTAMP" "$SHA" "${AUDIT_SHA:-}" > "$TMP_DIR/meta.json"

# --- strategy TTL metadata ---
TTL_FILE="$TMP_DIR/strategy_ttl.txt"
if [[ -d "$ROOT/strategies" ]]; then
    find "$ROOT/strategies" -name strategy.py | while read -r f; do
        strat="$(basename "$(dirname "$f")")"
        ttl="$(grep -m1 -E 'ttl_hours:' "$f" | awk '{print $2}')"
        mtime="$(date -u -r "$f" +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || echo unknown)"
        echo "$strat ttl_hours=${ttl:-na} modified=$mtime" >> "$TTL_FILE"
    done
else
    : > "$TTL_FILE"
fi

# --- capital gate summary ---
if [[ -f "$ROOT/logs/scoreboard.json" ]]; then
    python3.11 - "$ROOT/logs/scoreboard.json" "$TMP_DIR/capital_gate.json" <<'PY'
import json, statistics, sys
try:
    data = json.load(open(sys.argv[1]))
except Exception:
    data = []
vals = [float(d.get("pnl", 0)) for d in data]
sharpe = [float(d.get("sharpe", 0)) for d in data]
draw = [float(d.get("drawdown", 0)) for d in data]
res = {
    "median_pnl": statistics.median(vals) if vals else 0.0,
    "median_sharpe": statistics.median(sharpe) if sharpe else 0.0,
    "max_drawdown": max(draw) if draw else 0.0,
}
json.dump(res, open(sys.argv[2], "w"))
PY
fi

copy_item() {
    local p="$1"
    if [[ -e "$ROOT/$p" ]]; then
        local tgt="$TMP_DIR/$(basename "$p")"
        if [[ -L "$ROOT/$p" ]]; then
            return
        fi
        if [[ -d "$ROOT/$p" ]]; then
            cp -r "$ROOT/$p" "$tgt"
        else
            cp "$ROOT/$p" "$tgt"
        fi
    fi
}

copy_item last_3_codex_diffs
copy_item vault_export.json
copy_item config.yaml
copy_item .env
copy_item sim/results
copy_item logs/scoreboard.json
copy_item "$TTL_FILE"
copy_item "$TMP_DIR/meta.json"
copy_item "$TMP_DIR/capital_gate.json"

if [[ $DRY -eq 1 ]]; then
    echo "DRY RUN: would create $EXPORT_DIR/$ARCHIVE" && ls -R "$TMP_DIR"
    exit 0
fi

mkdir -p "$EXPORT_DIR"

tar -czf "$EXPORT_DIR/$ARCHIVE" -C "$TMP_DIR" .
echo "Export created at $EXPORT_DIR/$ARCHIVE"
