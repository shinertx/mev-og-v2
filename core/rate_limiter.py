"""Simple thread-safe rate limiter for external calls."""

from __future__ import annotations

import threading
import time


class RateLimiter:
    """Limit how often actions can be performed."""

    def __init__(self, rate: float) -> None:
        if rate <= 0:
            raise ValueError("rate must be > 0")
        self.rate = rate
        self._allow_at = time.monotonic()
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next action is allowed."""
        with self._lock:
            now = time.monotonic()
            if now < self._allow_at:
                time.sleep(self._allow_at - now)
            self._allow_at = max(now, self._allow_at) + 1 / self.rate
