from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from core.logger import StructuredLogger

LOG = StructuredLogger("founder_gate")
TOKEN_ENV = "FOUNDER_TOKEN"
TOKEN_FILE_ENV = "FOUNDER_TOKEN_FILE"
DEFAULT_TOKEN_PATH = "./founder.token"


def _token() -> Optional[str]:
    env_token = os.getenv(TOKEN_ENV)
    if env_token:
        return env_token
    path = Path(os.getenv(TOKEN_FILE_ENV, DEFAULT_TOKEN_PATH))
    if path.exists():
        try:
            return path.read_text().strip()
        except Exception:
            return None
    return None


def founder_approved(action: str = "generic") -> bool:
    token = _token()
    approved = False
    source = "none"
    if token:
        source = "env" if os.getenv(TOKEN_ENV) else "file"
        try:
            if ":" in token:
                t_action, ts = token.split(":", 1)
                if t_action == action and float(ts) > time.time():
                    approved = True
            else:
                approved = True
        except Exception:
            approved = False
    LOG.log("founder_check", action=action, approved=approved, source=source)
    return approved


def require_founder(action: str) -> None:
    if not founder_approved(action):
        raise PermissionError("Founder approval required")
