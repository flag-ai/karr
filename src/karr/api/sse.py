"""Server-sent events for the environment log relay (K-D2).

Framing follows Go: each log line becomes ``data: <line>\\n\\n`` with embedded
``\\r`` and ``\\n`` escaped as the two-character sequences ``\\r`` and ``\\n``
so a line can never inject a frame. Unlike Go the backslash itself is escaped
first (``\\`` -> ``\\\\``), so a literal ``\\n`` in a log line survives the
round trip through the SPA's unescape. New here: a ``: keepalive`` comment
every ``keepalive_seconds`` so idle proxies keep the connection, an
``event: end`` frame when the upstream stream closes, and ``event: error``
with a message when it fails, instead of silently ending.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

from fastapi.responses import StreamingResponse
from flag_commons.bonnie import BonnieError
from starlette.types import Receive, Scope, Send

DEFAULT_KEEPALIVE_SECONDS = 15.0
QUEUE_MAX_LINES = 1000  # backpressure: a stalled client stops the upstream read
MAX_STREAM_SECONDS = 4 * 3600.0  # a viewer left open must not hold a connection forever
MAX_STREAMS_PER_KEY = (
    8  # open log streams per agent: each is a live docker logs on the host
)
MAX_STREAMS_PER_CLIENT = (
    3  # per (agent, client): one flaky viewer cannot fill the agent's cap
)
LEASE_GRACE_SECONDS = 300.0  # a lease older than the stream limit plus this is evicted
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_log = logging.getLogger(__name__)


def escape_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def data_frame(line: str) -> str:
    return f"data: {escape_line(line)}\n\n"


def event_frame(event: str, data: str = "") -> str:
    return f"event: {event}\ndata: {escape_line(data)}\n\n"


KEEPALIVE_FRAME = ": keepalive\n\n"


@dataclass
class _Lease:
    key: str
    client: str
    started: float


class StreamSlots:
    """Counts open relays per key (an agent id) and per client, refusing past the caps.

    Every open log stream is a live ``docker logs`` on the host; the caps keep
    one agent from serving unbounded viewers and one client (an operator on a
    flaky link whose dead relays have not timed out yet) from filling the
    agent's cap. Leases also expire after the stream limit plus a grace, so a
    release that never came cannot lock an agent out for the process lifetime.
    """

    def __init__(
        self,
        per_key: int = MAX_STREAMS_PER_KEY,
        per_client: int = MAX_STREAMS_PER_CLIENT,
        *,
        max_age: float = MAX_STREAM_SECONDS + LEASE_GRACE_SECONDS,
    ) -> None:
        self.per_key = per_key
        self.per_client = per_client
        self.max_age = max_age
        self._leases: dict[int, _Lease] = {}
        self._next = 1

    def _evict_expired(self, now: float) -> None:
        for lease_id, lease in list(self._leases.items()):
            if now - lease.started > self.max_age:
                _log.warning(
                    "log stream lease for agent %s expired without release", lease.key
                )
                del self._leases[lease_id]

    def open(self, key: str, client: str | None = None) -> int:
        """Open streams for ``key`` (optionally only those of ``client``)."""
        return sum(
            1
            for lease in self._leases.values()
            if lease.key == key and (client is None or lease.client == client)
        )

    def acquire(self, key: str, client: str = "") -> Callable[[], None]:
        """Take a slot and return the idempotent release callback, or raise."""
        now = time.monotonic()
        self._evict_expired(now)
        if self.open(key) >= self.per_key:
            raise TooManyStreams(
                f"too many open log streams for this agent (limit {self.per_key})"
            )
        if self.open(key, client) >= self.per_client:
            raise TooManyStreams(
                f"too many open log streams from this client for the agent (limit {self.per_client})"
            )
        lease_id = self._next
        self._next += 1
        self._leases[lease_id] = _Lease(key, client, now)

        def release() -> None:
            self._leases.pop(lease_id, None)

        return release


class TooManyStreams(Exception):
    pass


_BACKGROUND: set[asyncio.Task[Any]] = set()


def _detach(coro: Any) -> None:
    """Run ``coro`` outside the current cancel scope (a cancelled relay cannot await)."""
    task = asyncio.get_running_loop().create_task(coro)
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)


async def _close_upstream(lines: AsyncIterator[str]) -> None:
    aclose = getattr(lines, "aclose", None)
    if aclose is not None:
        with contextlib.suppress(Exception):
            await aclose()


async def relay(
    lines: AsyncIterator[str],
    *,
    keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS,
    max_seconds: float = MAX_STREAM_SECONDS,
    on_close: Callable[[], None] | None = None,
) -> AsyncIterator[str]:
    """Turn upstream log lines into SSE frames with keepalives and a terminal event.

    The stream ends with ``event: end`` after ``max_seconds`` even if the
    container keeps logging; ``on_close`` runs exactly once when the relay is
    finished, cancelled by a client disconnect, or garbage collected.
    """
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue(
        maxsize=QUEUE_MAX_LINES
    )
    deadline = asyncio.get_running_loop().time() + max_seconds

    async def pump() -> None:
        try:
            async for line in lines:
                await queue.put(("line", line))
            await queue.put(("end", None))
        except asyncio.CancelledError:
            raise
        except BonnieError as exc:  # sanitised by flag-commons: safe to relay
            _log.warning("log stream ended with error: %s", exc)
            await queue.put(("error", exc.message))
        except Exception as exc:  # noqa: BLE001 - reported to the client as an error event
            _log.warning("log stream ended with error: %s", exc, exc_info=exc)
            await queue.put(("error", f"stream failed: {exc.__class__.__name__}"))

    task = asyncio.create_task(pump())
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                yield event_frame(
                    "end", "stream time limit reached; reconnect to continue"
                )
                return
            # asyncio.wait, not wait_for: on Python 3.10 wait_for swallows a
            # cancellation that lands as the item arrives, and a swallowed
            # client-disconnect would keep this relay (and its BONNIE stream)
            # alive. wait() re-raises cancellation; the getter is cancelled here.
            getter = asyncio.ensure_future(queue.get())
            try:
                done, _ = await asyncio.wait(
                    {getter}, timeout=min(keepalive_seconds, remaining)
                )
            except BaseException:
                getter.cancel()
                raise
            if not done:
                getter.cancel()
                if deadline - asyncio.get_running_loop().time() > 0:
                    yield KEEPALIVE_FRAME
                continue
            kind, payload = getter.result()
            if kind == "line":
                yield data_frame(payload or "")
            elif kind == "end":
                yield event_frame("end")
                return
            else:
                yield event_frame("error", payload or "stream failed")
                return
    finally:
        # A client disconnect reaches us as cancellation, and anyio re-delivers
        # it at every await: the upstream close (an httpx connection release
        # that does suspend) must therefore run as a detached task, and the
        # slot release must not sit behind any await at all.
        try:
            task.cancel()
            _detach(_close_upstream(lines))
        finally:
            if on_close is not None:
                on_close()


class SSEResponse(StreamingResponse):
    """A StreamingResponse whose cleanup runs on every exit, started or not.

    Under uvicorn (ASGI spec 2.3) a client disconnect cancels the streaming
    task; if the client was gone before the first frame the relay generator
    was never even started, and ``aclose()`` on an unstarted generator skips
    its ``finally``. ``on_close`` therefore runs from here as well, and
    ``aclosing`` covers the spec 2.4 path where a failed ``send`` raises.
    """

    def __init__(
        self, *args: Any, on_close: Callable[[], None] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(*args, **kwargs)
        self._on_close = on_close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        iterator = self.body_iterator
        try:
            if hasattr(iterator, "aclose"):
                async with contextlib.aclosing(iterator):  # type: ignore[type-var]
                    await super().__call__(scope, receive, send)
            else:
                await super().__call__(scope, receive, send)
        finally:
            if self._on_close is not None:
                self._on_close()


def sse_response(
    frames: AsyncIterator[str], *, on_close: Callable[[], None] | None = None
) -> StreamingResponse:
    return SSEResponse(
        frames, media_type="text/event-stream", headers=SSE_HEADERS, on_close=on_close
    )
