from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from karr.api.sse import KEEPALIVE_FRAME, data_frame, escape_line, event_frame, relay

pytestmark = pytest.mark.anyio


def test_framing_matches_go() -> None:
    assert data_frame("hello") == "data: hello\n\n"
    assert escape_line("a\r\nb") == "a\\r\\nb"  # K-D2: no frame injection
    assert data_frame("x\n\ndata: forged") == "data: x\\n\\ndata: forged\n\n"
    assert event_frame("end") == "event: end\ndata: \n\n"
    assert event_frame("error", "boom\n") == "event: error\ndata: boom\\n\n\n"


async def _lines(
    *items: str, delay: float = 0.0, fail: str | None = None
) -> AsyncIterator[str]:
    for item in items:
        if delay:
            await asyncio.sleep(delay)
        yield item
    if fail:
        raise RuntimeError(fail)


async def test_relay_emits_lines_and_end() -> None:
    frames = [f async for f in relay(_lines("one", "two"), keepalive_seconds=5)]
    assert frames == ["data: one\n\n", "data: two\n\n", "event: end\ndata: \n\n"]


async def test_relay_keepalive_and_error() -> None:
    frames = [
        f
        async for f in relay(
            _lines("late", delay=0.12, fail="upstream gone"), keepalive_seconds=0.05
        )
    ]
    assert KEEPALIVE_FRAME in frames
    assert frames[-2] == "data: late\n\n"
    assert frames[-1] == "event: error\ndata: upstream gone\n\n"


async def test_relay_stops_pump_when_consumer_leaves() -> None:
    seen = 0

    async def endless() -> AsyncIterator[str]:
        nonlocal seen
        while True:
            seen += 1
            yield "tick"
            await asyncio.sleep(0.001)

    gen = relay(endless(), keepalive_seconds=1)
    assert await gen.__anext__() == "data: tick\n\n"
    await gen.aclose()
    await asyncio.sleep(0.02)
    before = seen
    await asyncio.sleep(0.02)
    assert seen == before  # the pump task was cancelled


async def test_relay_applies_backpressure_and_closes_upstream() -> None:
    from karr.api.sse import QUEUE_MAX_LINES

    produced = 0
    closed = False

    async def endless() -> AsyncIterator[str]:
        nonlocal produced, closed
        try:
            while True:
                produced += 1
                yield "tick"
        finally:
            closed = True

    gen = relay(endless(), keepalive_seconds=5)
    assert await gen.__anext__() == "data: tick\n\n"
    await asyncio.sleep(0.05)  # the consumer stalls; the pump must not run away
    assert produced <= QUEUE_MAX_LINES + 2
    await gen.aclose()
    assert closed  # the upstream generator was closed, releasing its connection
