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
from collections import Counter
from collections.abc import AsyncIterator, Callable

from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

DEFAULT_KEEPALIVE_SECONDS = 15.0
QUEUE_MAX_LINES = 1000  # backpressure: a stalled client stops the upstream read
MAX_STREAM_SECONDS = 4 * 3600.0  # a viewer left open must not hold a connection forever
MAX_STREAMS_PER_KEY = (
    8  # the per-agent httpx pool is shared with health and control calls
)
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_log = logging.getLogger(__name__)


def escape_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def data_frame(line: str) -> str:
    return f"data: {escape_line(line)}\n\n"


def event_frame(event: str, data: str = "") -> str:
    return f"event: {event}\ndata: {escape_line(data)}\n\n"


KEEPALIVE_FRAME = ": keepalive\n\n"


class StreamSlots:
    """Counts open relays per key (an agent id) and refuses past the cap.

    Every open log stream holds one connection out of that agent's HTTP pool;
    unbounded viewers would starve the registry poll and control calls.
    """

    def __init__(self, per_key: int = MAX_STREAMS_PER_KEY) -> None:
        self.per_key = per_key
        self._open: Counter[str] = Counter()

    def open(self, key: str) -> int:
        return self._open[key]

    def acquire(self, key: str) -> Callable[[], None]:
        """Take a slot and return the idempotent release callback, or raise."""
        if self._open[key] >= self.per_key:
            raise TooManyStreams(key, self.per_key)
        self._open[key] += 1
        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            self._open[key] -= 1
            if self._open[key] <= 0:
                del self._open[key]

        return release


class TooManyStreams(Exception):
    def __init__(self, key: str, limit: int) -> None:
        super().__init__(f"too many open log streams (limit {limit})")
        self.key = key
        self.limit = limit


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
        except Exception as exc:  # noqa: BLE001 - reported to the client as an error event
            _log.warning("log stream ended with error: %s", exc)
            await queue.put(("error", str(exc) or exc.__class__.__name__))

    task = asyncio.create_task(pump())
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                yield event_frame(
                    "end", "stream time limit reached; reconnect to continue"
                )
                return
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=min(keepalive_seconds, remaining)
                )
            except asyncio.TimeoutError:
                if deadline - asyncio.get_running_loop().time() > 0:
                    yield KEEPALIVE_FRAME
                continue
            if kind == "line":
                yield data_frame(payload or "")
            elif kind == "end":
                yield event_frame("end")
                return
            else:
                yield event_frame("error", payload or "stream failed")
                return
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        aclose = getattr(lines, "aclose", None)
        if aclose is not None:  # release the upstream BONNIE connection promptly
            with contextlib.suppress(Exception):
                await aclose()
        if on_close is not None:
            on_close()


class SSEResponse(StreamingResponse):
    """A StreamingResponse that closes its generator the moment the send fails.

    Under uvicorn (ASGI spec 2.4) a client disconnect surfaces as an OSError
    from ``send`` in the consumer, which leaves a plain async generator
    suspended until the garbage collector finalises it. ``aclosing`` runs the
    relay's ``finally`` (pump cancel, upstream close, slot release) on every
    exit path instead.
    """

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        iterator = self.body_iterator
        if hasattr(iterator, "aclose"):
            async with contextlib.aclosing(iterator):  # type: ignore[type-var]
                await super().__call__(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)


def sse_response(frames: AsyncIterator[str]) -> StreamingResponse:
    return SSEResponse(frames, media_type="text/event-stream", headers=SSE_HEADERS)
