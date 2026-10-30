"""Tiny in-memory sliding-window limiter for unauthenticated endpoints."""

from __future__ import annotations

import time
from collections import defaultdict, deque


class FailureLimiter:
    """Blocks a key after too many recorded failures inside the window."""

    def __init__(self, max_failures: int, window_seconds: float) -> None:
        self.max_failures = max_failures
        self.window = window_seconds
        self._failures: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str) -> deque[float]:
        events = self._failures[key]
        cutoff = time.monotonic() - self.window
        while events and events[0] < cutoff:
            events.popleft()
        return events

    def blocked(self, key: str) -> bool:
        return len(self._prune(key)) >= self.max_failures

    def record_failure(self, key: str) -> None:
        self._prune(key).append(time.monotonic())

    def reset(self) -> None:
        self._failures.clear()


pairing_limiter = FailureLimiter(max_failures=8, window_seconds=300)
