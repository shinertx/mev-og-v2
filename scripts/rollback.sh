#!/bin/bash

# Restore state from the latest DRP snapshot archive.
# Usage: scripts/rollback.sh [--archive=<file>] [--export-dir=<dir>]
# Example: scripts/rollback.sh --archive=export/drp_export_2025-05-26T00-00-00Z.tar.gz

set -euo pipefail

EXPORT_DIR="${EXPORT_DIR:-export}"
ARCHIVE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --archive=*)
            ARCHIVE="${1#*=}"
            shift
            ;;
        --export-dir=*)
            EXPORT_DIR="${1#*=}"
            shift
            ;;
        *)
            echo "Usage: $0 [--archive=<file>] [--export-dir=<dir>]" >&2
            exit 1
            ;;
    esac
done

LOG_FILE="${ERROR_LOG_FILE:-logs/errors.log}"
AUDIT_LOG="${ROLLBACK_LOG_FILE:-logs/rollback.log}"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

log_event() {
    mkdir -p "$(dirname "$AUDIT_LOG")"
    printf '{"timestamp":"%s","event":"%s","archive":"%s"}\n' "$TIMESTAMP" "$1" "$2" >> "$AUDIT_LOG"
}

if [[ -z "$ARCHIVE" ]]; then
    ARCHIVE=$(ls -1t "$EXPORT_DIR"/drp_export_*.tar.* 2>/dev/null | head -n1 || true)
fi

if [[ -z "$ARCHIVE" || ! -f "$ARCHIVE" ]]; then
    mkdir -p "$(dirname "$LOG_FILE")"
    echo "$TIMESTAMP rollback_failed archive_not_found" >> "$LOG_FILE"
    log_event "failed" "$ARCHIVE"
    echo "No DRP archive found" >&2
    exit 1
fi

# decrypt if needed
if [[ "$ARCHIVE" == *.enc ]]; then
    if [[ -z "${DRP_ENC_KEY:-}" ]]; then
        echo "DRP_ENC_KEY required for decryption" >&2
        exit 1
    fi
    if command -v openssl >/dev/null 2>&1; then
        echo -n "$DRP_ENC_KEY" | \
            openssl enc -d -aes-256-cbc -pbkdf2 -pass stdin \
            -in "$ARCHIVE" -out "${ARCHIVE%.enc}"
        ARCHIVE="${ARCHIVE%.enc}"
    elif command -v gpg >/dev/null 2>&1; then
        echo "$DRP_ENC_KEY" | \
            gpg --batch --yes --passphrase-fd 0 -o "${ARCHIVE%.enc}" -d "$ARCHIVE"
        ARCHIVE="${ARCHIVE%.enc}"
    else
        echo "No openssl or gpg available for decryption" >&2
        exit 1
    fi
fi

if [[ "$ARCHIVE" == *.gpg ]]; then
    if [[ -z "${DRP_ENC_KEY:-}" ]]; then
        echo "DRP_ENC_KEY required for decryption" >&2
        exit 1
    fi
    if command -v gpg >/dev/null 2>&1; then
        echo "$DRP_ENC_KEY" | \
            gpg --batch --yes --passphrase-fd 0 -o "${ARCHIVE%.gpg}" -d "$ARCHIVE"
        ARCHIVE="${ARCHIVE%.gpg}"
    elif command -v openssl >/dev/null 2>&1; then
        echo -n "$DRP_ENC_KEY" | \
            openssl enc -d -aes-256-cbc -pbkdf2 -pass stdin \
            -in "$ARCHIVE" -out "${ARCHIVE%.gpg}"
        ARCHIVE="${ARCHIVE%.gpg}"
    else
        echo "No openssl or gpg available for decryption" >&2
        exit 1
    fi
fi

# Extract archive relative to repo root
 tar -xzf "$ARCHIVE"
log_event "restore" "$ARCHIVE"
mkdir -p "$(dirname "$LOG_FILE")"
echo "$TIMESTAMP restored $ARCHIVE" >> "$LOG_FILE"
