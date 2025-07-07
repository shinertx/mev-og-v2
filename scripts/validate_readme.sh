#!/usr/bin/env bash
# Validate README formatting and links
set -euo pipefail

README="README.md"

if command -v shellcheck >/dev/null 2>&1; then
  shellcheck scripts/*.sh
fi

if command -v linkchecker >/dev/null 2>&1; then
  linkchecker "$README" --quiet
fi

# Gather required environment variables from codebase
vars=$(grep -horE '\$\{([A-Z0-9_]+)[^}]*\}' config*.yaml docker-compose.yml Dockerfile* scripts/*.sh 2>/dev/null \
        | sed -E 's/\$\{([A-Z0-9_]+).*/\1/' | sort -u)
# ignore cosmetic and internal vars
vars=$(echo "$vars" | grep -Ev '^(GREEN|RED|YELLOW|NC|ARCHIVE|EXPORT_NAME|EXPORT_PATH|NAME|AUDIT_SHA|TIMESTAMP)$')

missing=""
for v in $vars; do
    if ! grep -q "$v" "$README"; then
        missing+="$v\n"
    fi
done

if [[ -n "$missing" ]]; then
    echo "README missing environment variables:" >&2
    echo -e "$missing" >&2
    exit 1
fi

echo "README validation passed."
