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
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

DEFAULT_KEEPALIVE_SECONDS = 15.0
QUEUE_MAX_LINES = 1000  # backpressure: a stalled client stops the upstream read
SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}

_log = logging.getLogger(__name__)


def escape_line(line: str) -> str:
    return line.replace("\\", "\\\\").replace("\r", "\\r").replace("\n", "\\n")


def data_frame(line: str) -> str:
    return f"data: {escape_line(line)}\n\n"


def event_frame(event: str, data: str = "") -> str:
    return f"event: {event}\ndata: {escape_line(data)}\n\n"


KEEPALIVE_FRAME = ": keepalive\n\n"


async def relay(
    lines: AsyncIterator[str], *, keepalive_seconds: float = DEFAULT_KEEPALIVE_SECONDS
) -> AsyncIterator[str]:
    """Turn upstream log lines into SSE frames with keepalives and a terminal event."""
    queue: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue(
        maxsize=QUEUE_MAX_LINES
    )

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
            try:
                kind, payload = await asyncio.wait_for(
                    queue.get(), timeout=keepalive_seconds
                )
            except asyncio.TimeoutError:
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


def sse_response(frames: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(
        frames, media_type="text/event-stream", headers=SSE_HEADERS
    )
