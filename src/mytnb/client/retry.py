"""Bounded retry with exponential backoff for transient transport failures.

The myTNB APIs sit behind CloudFront/WAF and intermittently return transient
errors (a spurious 404, occasional 5xx, or a dropped connection) that succeed
on an immediate retry. This helper absorbs those blips inside a single call so
that a one-off failure does not surface as a hard error to callers.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Awaitable, Callable, TypeVar

import httpx
from curl_cffi.requests.exceptions import RequestException as CurlRequestException

from mytnb.exceptions import MyTNBError

T = TypeVar("T")

# HTTP statuses treated as transient. 404 is unusual to retry, but for this
# WAF-fronted API it is a known intermittent edge failure, not a real
# "not found". 429 is deliberately excluded — retrying a rate limiter only
# makes it worse; let RateLimitError propagate.
RETRYABLE_STATUS_CODES = frozenset({404, 500, 502, 503, 504})

# Network/transport-level errors that are always safe to retry.
_RETRYABLE_EXCEPTIONS = (
    httpx.TransportError,
    httpx.TimeoutException,
    CurlRequestException,
)

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY = 0.5


def _is_retryable(err: Exception) -> bool:
    """Return True if the error is a transient failure worth retrying."""
    if isinstance(err, _RETRYABLE_EXCEPTIONS):
        return True
    return isinstance(err, MyTNBError) and getattr(err, "retryable", False)


async def with_retry(
    send: Callable[[], Awaitable[T]],
    *,
    attempts: int = DEFAULT_MAX_ATTEMPTS,
    base_delay: float = DEFAULT_BASE_DELAY,
    logger: logging.Logger | None = None,
) -> T:
    """Call ``send`` with exponential backoff on transient failures.

    Args:
        send: Zero-arg coroutine factory performing one request attempt.
        attempts: Maximum number of attempts (including the first).
        base_delay: Base backoff delay in seconds (with added jitter).
        logger: Optional logger for debug messages between retries.

    Returns:
        Whatever ``send`` returns on the first successful attempt.

    Raises:
        ValueError: If ``attempts`` < 1 or ``base_delay`` < 0.
        The last exception raised by ``send`` once attempts are exhausted, or
        immediately for any non-retryable error.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    if base_delay < 0:
        raise ValueError(f"base_delay must be >= 0, got {base_delay}")

    for attempt in range(attempts):
        try:
            return await send()
        except Exception as err:  # noqa: BLE001 - re-raised below unless retryable
            if attempt >= attempts - 1 or not _is_retryable(err):
                raise
            delay = base_delay * 2**attempt + random.uniform(0, base_delay)
            if logger is not None:
                logger.debug(
                    "Transient request failure (attempt %d/%d), retrying in %.2fs: %s",
                    attempt + 1,
                    attempts,
                    delay,
                    err,
                )
            await asyncio.sleep(delay)
    # Unreachable: the loop either returns or raises on the final attempt.
    raise RuntimeError("with_retry exhausted attempts without returning")
