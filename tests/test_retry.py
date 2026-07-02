"""Tests for the transport retry helper."""

import httpx
import pytest

from mytnb.client.retry import RETRYABLE_STATUS_CODES, with_retry
from mytnb.exceptions import APIError, AuthenticationError


class _Counter:
    """Callable that records how many times it was awaited."""

    def __init__(self, side_effect):
        self.calls = 0
        self._side_effect = side_effect

    async def __call__(self):
        self.calls += 1
        result = self._side_effect(self.calls)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.asyncio
async def test_returns_on_first_success():
    send = _Counter(lambda n: "ok")
    result = await with_retry(send, base_delay=0)
    assert result == "ok"
    assert send.calls == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    def effect(n):
        if n < 3:
            return APIError("transient", error_code="503", retryable=True)
        return "ok"

    send = _Counter(effect)
    result = await with_retry(send, attempts=3, base_delay=0)
    assert result == "ok"
    assert send.calls == 3


@pytest.mark.asyncio
async def test_gives_up_after_attempts():
    send = _Counter(lambda n: APIError("still failing", error_code="503", retryable=True))
    with pytest.raises(APIError, match="still failing"):
        await with_retry(send, attempts=3, base_delay=0)
    assert send.calls == 3


@pytest.mark.asyncio
async def test_does_not_retry_non_retryable():
    send = _Counter(lambda n: AuthenticationError("bad creds", error_code="401"))
    with pytest.raises(AuthenticationError):
        await with_retry(send, attempts=3, base_delay=0)
    assert send.calls == 1


@pytest.mark.asyncio
async def test_non_retryable_api_error_not_retried():
    # An APIError without retryable=True (e.g. a business error) is terminal.
    send = _Counter(lambda n: APIError("business error", error_code="5000"))
    with pytest.raises(APIError, match="business error"):
        await with_retry(send, attempts=3, base_delay=0)
    assert send.calls == 1


@pytest.mark.asyncio
async def test_network_error_is_retryable():
    def effect(n):
        if n < 2:
            return httpx.ConnectError("connection reset")
        return "ok"

    send = _Counter(effect)
    result = await with_retry(send, attempts=3, base_delay=0)
    assert result == "ok"
    assert send.calls == 2


@pytest.mark.asyncio
async def test_invalid_attempts_raises():
    send = _Counter(lambda n: "ok")
    with pytest.raises(ValueError, match="attempts must be >= 1"):
        await with_retry(send, attempts=0, base_delay=0)
    assert send.calls == 0


@pytest.mark.asyncio
async def test_invalid_base_delay_raises():
    send = _Counter(lambda n: "ok")
    with pytest.raises(ValueError, match="base_delay must be >= 0"):
        await with_retry(send, base_delay=-1)
    assert send.calls == 0


def test_retryable_status_codes():
    assert 404 in RETRYABLE_STATUS_CODES
    assert 503 in RETRYABLE_STATUS_CODES
    # Auth / geoblock / rate-limit are handled separately, never retried here.
    assert 401 not in RETRYABLE_STATUS_CODES
    assert 403 not in RETRYABLE_STATUS_CODES
    assert 429 not in RETRYABLE_STATUS_CODES
