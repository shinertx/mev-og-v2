from __future__ import annotations

import os
from pathlib import Path


def get_secret(name: str) -> str:
    """Return secret ``name`` from environment or file path.

    The function first checks ``${name}_FILE`` for a file containing the
    secret. If found, the file's contents are returned. Otherwise the
    environment variable ``name`` is used. Raises ``RuntimeError`` if the
    secret is not found.
    """
    file_var = f"{name}_FILE"
    path = os.getenv(file_var)
    if path:
        p = Path(path)
        if p.exists():
            return p.read_text().strip()
    val = os.getenv(name)
    if val:
        return val
    raise RuntimeError(f"secret {name} not found")
