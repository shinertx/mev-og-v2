import time


from core.rate_limiter import RateLimiter


def test_rate_limit_waits():
    rl = RateLimiter(2)  # 2 actions per second
    start = time.monotonic()
    rl.wait()
    rl.wait()
    duration = time.monotonic() - start
    assert duration >= 0.5
