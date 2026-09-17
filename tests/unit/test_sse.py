from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from karr.api.sse import (
    KEEPALIVE_FRAME,
    StreamSlots,
    TooManyStreams,
    data_frame,
    escape_line,
    event_frame,
    relay,
)

pytestmark = pytest.mark.anyio


def test_framing_matches_go() -> None:
    assert data_frame("hello") == "data: hello\n\n"
    assert escape_line("a\r\nb") == "a\\r\\nb"  # K-D2: no frame injection
    assert (
        escape_line("C:\\new\\rows") == "C:\\\\new\\\\rows"
    )  # a literal \n stays literal
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
    # internal exception text stays in the log; the client sees the class only
    assert frames[-1] == "event: error\ndata: stream failed: RuntimeError\n\n"


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
    for _ in range(5):  # the upstream close runs as a detached task
        await asyncio.sleep(0)
    assert closed  # the upstream generator was closed, releasing its connection


def test_stream_slots_cap_per_key_per_client_and_expire() -> None:
    slots = StreamSlots(per_key=3, per_client=2, max_age=100)
    a1 = slots.acquire("agent-a", "10.0.0.1")
    slots.acquire("agent-a", "10.0.0.1")
    with pytest.raises(TooManyStreams, match="from this client"):
        slots.acquire("agent-a", "10.0.0.1")  # one viewer cannot take the whole cap
    slots.acquire("agent-a", "10.0.0.2")
    with pytest.raises(TooManyStreams, match="for this agent"):
        slots.acquire("agent-a", "10.0.0.3")
    slots.acquire("agent-b", "10.0.0.1")  # another agent is unaffected
    a1()
    a1()  # idempotent
    assert slots.open("agent-a") == 2 and slots.open("agent-a", "10.0.0.1") == 1
    slots.acquire("agent-a", "10.0.0.3")  # the freed slot is usable again
    # a lease whose release never came is evicted after max_age
    for lease in slots._leases.values():
        lease.started -= 1000
    slots.acquire("agent-a", "10.0.0.9")
    assert slots.open("agent-a") == 1


async def test_relay_ends_at_the_time_limit_and_runs_on_close() -> None:
    closed = 0

    def on_close() -> None:
        nonlocal closed
        closed += 1

    frames = [
        f
        async for f in relay(
            _lines("a", "b", "c", delay=0.03),
            keepalive_seconds=5,
            max_seconds=0.05,
            on_close=on_close,
        )
    ]
    assert frames[-1].startswith("event: end\ndata: stream time limit")
    assert len(frames) < 4  # the third line never made it
    assert closed == 1


async def test_relay_releases_slot_and_closes_upstream_when_cancelled() -> None:
    closed = 0
    upstream_closed = False

    def on_close() -> None:
        nonlocal closed
        closed += 1

    async def endless() -> AsyncIterator[str]:
        nonlocal upstream_closed
        try:
            while True:
                yield "tick"
                await asyncio.sleep(0.001)
        finally:
            # an httpx response release suspends; under a cancelled scope an
            # awaited aclose() would be aborted here, so the relay detaches it
            await asyncio.sleep(0)
            upstream_closed = True

    async def consume() -> None:
        async for _ in relay(endless(), keepalive_seconds=1, on_close=on_close):
            pass

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.02)
    task.cancel()  # what Starlette does on client disconnect
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == 1  # the slot went back synchronously
    for _ in range(5):
        await asyncio.sleep(0)
    assert upstream_closed  # ... and the upstream was closed by the detached task


async def test_relay_hides_internal_error_text() -> None:
    async def broken() -> AsyncIterator[str]:
        yield "one"
        raise OSError("/etc/hosts: connection to 10.1.2.3 refused")

    frames = [f async for f in relay(broken(), keepalive_seconds=5)]
    assert frames[-1] == "event: error\ndata: stream failed: OSError\n\n"
