#!/usr/bin/env python3.11
"""Validate required secrets are present and not placeholders."""

import os
import sys

REQUIRED = [
    "PRIVATE_KEY",
    "OPENAI_API_KEY",
    "FLASHBOTS_AUTH_KEY",
    "VAULT_ADDR",
    "VAULT_TOKEN",
]

missing = [name for name in REQUIRED if not os.getenv(name)]
if missing:
    print("Missing secrets: " + ", ".join(missing), file=sys.stderr)
    sys.exit(1)

placeholders = [n for n in REQUIRED if os.getenv(n, "").startswith("YOUR_")]
if placeholders:
    print("Placeholder secrets detected: " + ", ".join(placeholders), file=sys.stderr)
    sys.exit(1)

print("Secrets validation passed")
