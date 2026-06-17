import time
from collections import deque


class DailyQuotaExceededError(RuntimeError):
    """Raised when the daily request quota for the LLM API has been exhausted."""


class RateLimiter:
    """Token-bucket rate limiter enforcing per-minute and per-day request caps."""

    def __init__(self, rpm: int, rpd: int) -> None:
        self._rpm = rpm
        self._rpd = rpd
        self._minute_window: deque[float] = deque()
        self._day_count: int = 0

    def wait_if_needed(self) -> None:
        """Block until a request can be safely issued without exceeding rate limits.

        Raises DailyQuotaExceededError if the daily limit has already been reached.
        """
        if self._day_count >= self._rpd:
            raise DailyQuotaExceededError(
                f"Daily request quota of {self._rpd} exceeded. "
                "The agent will resume at the next calendar day."
            )

        now = time.monotonic()
        while self._minute_window and now - self._minute_window[0] > 60:
            self._minute_window.popleft()

        if len(self._minute_window) >= self._rpm:
            sleep_for = 60.0 - (now - self._minute_window[0]) + 0.1
            time.sleep(sleep_for)

    def record_request(self) -> None:
        """Record that a request was just issued."""
        self._minute_window.append(time.monotonic())
        self._day_count += 1
