"""Fan-out of live task and PC updates to the phones that are listening.

The database writers (HTTP handlers on worker threads, the PC's websocket on the event
loop) call `publish`; each listening phone has its own queue on its own event loop. Events
are full snapshots, so a phone that misses some of them only needs the latest one.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

MAX_SUBSCRIBERS_PER_USER = 5
QUEUE_SIZE = 200
RESYNC = {"type": "resync"}


@dataclass(eq=False)
class Subscriber:
    user_id: str
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=QUEUE_SIZE))

    def put(self, event: dict[str, Any]) -> None:
        """Runs on the subscriber's own loop. If the phone is too slow, drop the backlog and tell
        it to reload: it is cheaper than holding stale events for a client that is not reading."""
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            while not self.queue.empty():
                self.queue.get_nowait()
            self.queue.put_nowait(RESYNC)


class Hub:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[Subscriber]] = {}
        self._lock = threading.Lock()

    def subscribe(self, user_id: str, loop: asyncio.AbstractEventLoop) -> Subscriber | None:
        """None when this user already has too many open connections."""
        with self._lock:
            subs = self._subscribers.setdefault(user_id, set())
            if len(subs) >= MAX_SUBSCRIBERS_PER_USER:
                return None
            sub = Subscriber(user_id, loop)
            subs.add(sub)
            return sub

    def unsubscribe(self, sub: Subscriber) -> None:
        with self._lock:
            subs = self._subscribers.get(sub.user_id)
            if subs is not None:
                subs.discard(sub)
                if not subs:
                    del self._subscribers[sub.user_id]

    def count(self, user_id: str) -> int:
        with self._lock:
            return len(self._subscribers.get(user_id, ()))

    def publish(self, user_id: str, event: dict[str, Any]) -> None:
        """Safe to call from any thread. Only this user's phones ever see the event."""
        with self._lock:
            subs = list(self._subscribers.get(user_id, ()))
        for sub in subs:
            try:
                sub.loop.call_soon_threadsafe(sub.put, event)
            except RuntimeError:  # that phone's event loop has already closed
                self.unsubscribe(sub)

    def on_store_event(self, kind: str, user_id: str, payload: dict[str, Any]) -> None:
        self.publish(user_id, {"type": kind, kind: payload})


hub = Hub()
