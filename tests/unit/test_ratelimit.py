from __future__ import annotations

from karr.api.ratelimit import RateLimiter, TokenBucket


def test_token_bucket_refills_over_time() -> None:
    bucket = TokenBucket(2, refill_per_second=1.0, now=100.0)
    assert bucket.try_acquire(100.0) and bucket.try_acquire(100.0)
    assert not bucket.try_acquire(100.0)
    assert bucket.seconds_until_token() == 1.0
    assert not bucket.try_acquire(100.5)
    assert bucket.try_acquire(101.0)
    assert bucket.try_acquire(110.0) and bucket.try_acquire(110.0)  # capped at capacity
    assert not bucket.try_acquire(110.0)


def test_rate_limiter_is_keyed_and_bounded() -> None:
    limiter = RateLimiter(1, 0.0, max_clients=2)
    assert limiter.try_acquire("a") == (True, 0.0)
    allowed, retry = limiter.try_acquire("a")
    assert not allowed and retry == 0.0  # no refill configured: never
    assert limiter.try_acquire("b")[0]
    assert limiter.try_acquire("c")[0]  # evicts "a", the least recently used
    assert limiter.try_acquire("a")[0]  # fresh bucket after eviction
    limiter.reset()
    assert limiter.try_acquire("b")[0]
