"""Per-client token buckets for the provisioning routes (K-D23)."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from fastapi import Request
from fastapi.responses import JSONResponse

from karr.api.errors import ApiError

DEFAULT_MAX_CLIENTS = 10_000


class TokenBucket:
    """``capacity`` tokens, refilled at ``refill_per_second``."""

    def __init__(
        self, capacity: int, refill_per_second: float, *, now: float | None = None
    ) -> None:
        self.capacity = capacity
        self.refill = refill_per_second
        self._tokens = float(capacity)
        self._updated = time.monotonic() if now is None else now

    def try_acquire(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        self._tokens = min(
            self.capacity, self._tokens + (now - self._updated) * self.refill
        )
        self._updated = now
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

    def seconds_until_token(self) -> float:
        return (
            0.0
            if self._tokens >= 1 or self.refill <= 0
            else (1 - self._tokens) / self.refill
        )


class RateLimiter:
    """One bucket per client key with bounded LRU eviction; thread-safe.

    Keying by client means one abusive host cannot exhaust the budget for
    every other GPU host trying to register.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        *,
        max_clients: int = DEFAULT_MAX_CLIENTS,
    ) -> None:
        self.capacity = capacity
        self.refill = refill_per_second
        self.max_clients = max_clients
        self._buckets: OrderedDict[str, TokenBucket] = OrderedDict()
        self._lock = threading.Lock()

    def try_acquire(self, key: str) -> tuple[bool, float]:
        """Returns ``(allowed, retry_after_seconds)``."""
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = TokenBucket(self.capacity, self.refill)
                self._buckets[key] = bucket
                while len(self._buckets) > self.max_clients:
                    self._buckets.popitem(last=False)
            else:
                self._buckets.move_to_end(key)
            allowed = bucket.try_acquire()
            return allowed, 0.0 if allowed else bucket.seconds_until_token()

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


class RateLimited(ApiError):
    def __init__(self, retry_after: float) -> None:
        super().__init__(429, "rate limited; retry shortly")
        self.retry_after = max(1, int(retry_after + 0.999))

    def response(self) -> JSONResponse:
        return JSONResponse(
            {"error": self.message},
            status_code=429,
            headers={"Retry-After": str(self.retry_after)},
        )


def client_key(request: Request) -> str:
    return request.client.host if request.client and request.client.host else "unknown"


def rate_limited(limiter_name: str) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency using the :class:`RateLimiter` stored at ``app.state.<name>``."""

    async def dependency(request: Request) -> None:
        limiter: RateLimiter = getattr(request.app.state, limiter_name)
        allowed, retry_after = limiter.try_acquire(client_key(request))
        if not allowed:
            raise RateLimited(retry_after)

    return dependency
