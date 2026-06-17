import time
from collections import deque
from unittest.mock import patch

import pytest

from agent.infrastructure.rate_limiter import DailyQuotaExceededError, RateLimiter


def test_record_request_increments_day_count() -> None:
    limiter = RateLimiter(rpm=10, rpd=100)
    limiter.record_request()
    limiter.record_request()
    assert limiter._day_count == 2


def test_record_request_appends_to_minute_window() -> None:
    limiter = RateLimiter(rpm=10, rpd=100)
    limiter.record_request()
    assert len(limiter._minute_window) == 1


def test_daily_quota_raises_before_any_sleep() -> None:
    limiter = RateLimiter(rpm=100, rpd=2)
    limiter._day_count = 2
    with pytest.raises(DailyQuotaExceededError):
        limiter.wait_if_needed()


def test_minute_window_full_triggers_sleep() -> None:
    limiter = RateLimiter(rpm=3, rpd=100)
    now = time.monotonic()
    # Fill the window with recent timestamps
    limiter._minute_window = deque([now - 5, now - 3, now - 1])

    with patch("agent.infrastructure.rate_limiter.time.sleep") as mock_sleep:
        limiter.wait_if_needed()
        mock_sleep.assert_called_once()
        sleep_arg = mock_sleep.call_args[0][0]
        assert sleep_arg > 0


def test_minute_window_not_full_does_not_sleep() -> None:
    limiter = RateLimiter(rpm=5, rpd=100)
    limiter._minute_window = deque([time.monotonic() - 2])

    with patch("agent.infrastructure.rate_limiter.time.sleep") as mock_sleep:
        limiter.wait_if_needed()
        mock_sleep.assert_not_called()


def test_purge_only_expired_timestamps_keeps_recent() -> None:
    """Half the window is expired (>60s), half is recent — only expired ones are removed."""
    limiter = RateLimiter(rpm=5, rpd=100)
    with patch("agent.infrastructure.rate_limiter.time.monotonic", return_value=1000.0):
        limiter._minute_window = deque([880.0, 890.0, 900.0, 960.0, 970.0])
        with patch("agent.infrastructure.rate_limiter.time.sleep") as mock_sleep:
            limiter.wait_if_needed()
            mock_sleep.assert_not_called()
    assert len(limiter._minute_window) == 2


def test_old_timestamps_are_purged() -> None:
    limiter = RateLimiter(rpm=2, rpd=100)
    now = time.monotonic()
    # Two old timestamps (>60s ago) and one recent
    limiter._minute_window = deque([now - 120, now - 90, now - 1])

    with patch("agent.infrastructure.rate_limiter.time.sleep") as mock_sleep:
        limiter.wait_if_needed()
        # After purging the two old ones, only 1 remains — below rpm=2, no sleep
        mock_sleep.assert_not_called()
    assert len(limiter._minute_window) == 1
