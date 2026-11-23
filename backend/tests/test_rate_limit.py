from app.rate_limit import SlidingWindowRateLimiter


# Confirms a visitor is blocked only until the oldest request leaves the window.
def test_sliding_window_rate_limiter_returns_retry_time_and_recovers():
    current_time = [100.0]
    limiter = SlidingWindowRateLimiter(
        limit=2,
        window_seconds=60,
        clock=lambda: current_time[0],
    )

    assert limiter.consume("visitor").allowed is True
    assert limiter.consume("visitor").allowed is True

    blocked = limiter.consume("visitor")
    assert blocked.allowed is False
    assert blocked.retry_after == 60

    current_time[0] = 161.0
    assert limiter.consume("visitor").allowed is True


# Confirms an admin limit change takes effect without erasing the current window.
def test_sliding_window_rate_limiter_can_be_reconfigured_safely():
    limiter = SlidingWindowRateLimiter(
        limit=3,
        window_seconds=60,
        clock=lambda: 100.0,
    )
    assert limiter.consume("visitor").allowed is True
    assert limiter.consume("visitor").allowed is True

    limiter.reconfigure(limit=2)

    assert limiter.consume("visitor").allowed is False
    assert limiter.limit == 2
