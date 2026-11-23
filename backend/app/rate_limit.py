import math
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from threading import Lock


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: int = 0


# Keeps short-lived request timestamps in memory without logging visitor addresses.
class SlidingWindowRateLimiter:
    # Configures one request ceiling and allows tests to supply a predictable clock.
    def __init__(
        self,
        limit: int,
        window_seconds: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate limits and windows must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = Lock()
        self._last_cleanup = clock()

    # Records one request or returns the number of seconds until another is allowed.
    def consume(self, key: str) -> RateLimitDecision:
        now = self._clock()
        cutoff = now - self.window_seconds
        with self._lock:
            self._cleanup_inactive_keys(cutoff, now)
            events = self._events.setdefault(key, deque())
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= self.limit:
                retry_after = max(
                    1,
                    math.ceil(events[0] + self.window_seconds - now),
                )
                return RateLimitDecision(False, retry_after)
            events.append(now)
            return RateLimitDecision(True)

    # Applies a new ceiling while retaining requests already made in the active window.
    def reconfigure(self, *, limit: int) -> None:
        if limit < 1:
            raise ValueError("Rate limits must be positive")
        with self._lock:
            self.limit = limit

    # Periodically removes inactive visitors so abandoned counters do not accumulate.
    def _cleanup_inactive_keys(self, cutoff: float, now: float) -> None:
        if now - self._last_cleanup < self.window_seconds:
            return
        self._events = {
            key: events
            for key, events in self._events.items()
            if events and events[-1] > cutoff
        }
        self._last_cleanup = now
