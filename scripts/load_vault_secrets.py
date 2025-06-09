#!/usr/bin/env python3.11
"""Load secrets from HashiCorp Vault and output export commands."""

import os
import sys
from typing import Any

try:
    import hvac
except Exception as exc:  # pragma: no cover - hvac may not be installed in tests
    print(f"Error: hvac missing ({exc})", file=sys.stderr)
    sys.exit(1)

VAULT_ADDR = os.getenv("VAULT_ADDR")
VAULT_TOKEN = os.getenv("VAULT_TOKEN")
SECRET_PATH = os.getenv("VAULT_SECRET_PATH", "secret/data/mevog")

if not VAULT_ADDR or not VAULT_TOKEN:
    print("Error: VAULT_ADDR and VAULT_TOKEN must be set", file=sys.stderr)
    sys.exit(1)

client = hvac.Client(url=VAULT_ADDR, token=VAULT_TOKEN)
try:
    resp: Any = client.secrets.kv.v2.read_secret_version(path=SECRET_PATH)
except Exception as exc:  # pragma: no cover - network issues
    print(f"Error reading secrets: {exc}", file=sys.stderr)
    sys.exit(1)

for key, val in resp["data"]["data"].items():
    safe = str(val).replace("\n", "\\n").replace('"', '\\"')
    print(f'export {key}="{safe}"')
