"""Shared HTTP client: NEA rate limiting, retries with backoff, timeouts.

The NEA v2 realtime API allows 6 anonymous calls per 10 s (HTTP 429 above
that), so all NEA GETs share one RateLimiter. NASA FIRMS has its own (much
higher) quota and must NOT use the NEA limiter — pass limiter=None.
"""
from __future__ import annotations

import logging
import time
from collections import deque
from threading import Lock

import requests

import config

log = logging.getLogger(__name__)

DEFAULT_HEADERS = {"User-Agent": config.USER_AGENT}

# Patchable in tests so retry/backoff paths run fast.
_sleep = time.sleep


class RateLimiter:
    """Sliding-window call limiter (deque of call timestamps)."""

    def __init__(self, max_calls: int, window_s: float):
        self.max_calls = max_calls
        self.window_s = window_s
        self._calls: deque[float] = deque()
        self._lock = Lock()

    def wait_for_slot(self) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(now)
            if len(self._calls) >= self.max_calls:
                # Sleep until the oldest call leaves the window (+ small jitter).
                _sleep(self._calls[0] + self.window_s - now + 0.2)
                now = time.monotonic()
                self._prune(now)
            self._calls.append(now)

    def _prune(self, now: float) -> None:
        while self._calls and self._calls[0] <= now - self.window_s:
            self._calls.popleft()


# Shared limiter for all NEA endpoints.
NEA_LIMITER = RateLimiter(config.NEA_RATE_LIMIT_CALLS, config.NEA_RATE_LIMIT_WINDOW_S)

_default_session: requests.Session | None = None


def _session() -> requests.Session:
    global _default_session
    if _default_session is None:
        _default_session = requests.Session()
    return _default_session


def http_get(
    url: str,
    *,
    session: requests.Session | None = None,
    limiter: RateLimiter | None = None,
    params: dict | None = None,
    headers: dict | None = None,
    timeout: float = 20.0,
) -> requests.Response:
    """GET with retry/backoff. Honors Retry-After on 429. Raises on final failure."""
    session = session or _session()
    req_headers = {**DEFAULT_HEADERS, **(headers or {})}
    last_exc: Exception | None = None
    for attempt in range(config.HTTP_RETRIES):
        if limiter is not None:
            limiter.wait_for_slot()
        try:
            resp = session.get(url, params=params, headers=req_headers, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("GET %s attempt %d failed: %s", url, attempt + 1, exc)
            _sleep(config.HTTP_BACKOFF_FACTOR**attempt)
            continue
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "")
            delay = float(retry_after) if retry_after.isdigit() else config.HTTP_BACKOFF_FACTOR**attempt
            log.warning("GET %s rate-limited (429); waiting %.1fs", url, delay)
            _sleep(delay)
            continue
        if resp.status_code >= 500:
            log.warning("GET %s server error %d; retrying", url, resp.status_code)
            _sleep(config.HTTP_BACKOFF_FACTOR**attempt)
            continue
        return resp
    raise last_exc or RuntimeError(f"GET {url} failed after {config.HTTP_RETRIES} attempts")


def http_post_form(
    url: str,
    data: dict,
    *,
    session: requests.Session | None = None,
    limiter: RateLimiter | None = None,
    timeout: float = 20.0,
) -> requests.Response:
    """POST form-encoded (ASMC AJAX endpoints) with the same retry policy."""
    session = session or _session()
    last_exc: Exception | None = None
    for attempt in range(config.HTTP_RETRIES):
        if limiter is not None:
            limiter.wait_for_slot()
        try:
            resp = session.post(url, data=data, headers=DEFAULT_HEADERS, timeout=timeout)
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("POST %s attempt %d failed: %s", url, attempt + 1, exc)
            _sleep(config.HTTP_BACKOFF_FACTOR**attempt)
            continue
        if resp.status_code >= 500:
            log.warning("POST %s server error %d; retrying", url, resp.status_code)
            _sleep(config.HTTP_BACKOFF_FACTOR**attempt)
            continue
        return resp
    raise last_exc or RuntimeError(f"POST {url} failed after {config.HTTP_RETRIES} attempts")
