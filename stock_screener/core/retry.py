"""Reusable retry policies built on Tenacity."""

from __future__ import annotations

from typing import Awaitable, Callable, TypeVar

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from .errors import RateLimitError, UnavailableError

T = TypeVar("T")


def transient_provider_retry(
    *, attempts: int = 4, max_wait_s: float = 8.0
) -> AsyncRetrying:
    """Retry on transient provider errors (rate-limit / unavailable)."""
    return AsyncRetrying(
        retry=retry_if_exception_type((RateLimitError, UnavailableError)),
        stop=stop_after_attempt(attempts),
        wait=wait_exponential_jitter(initial=0.5, max=max_wait_s),
        reraise=True,
    )


async def with_retry(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 4,
    max_wait_s: float = 8.0,
) -> T:
    """Run ``fn`` with the standard transient-provider retry policy."""
    try:
        async for attempt in transient_provider_retry(attempts=attempts, max_wait_s=max_wait_s):
            with attempt:
                return await fn()
    except RetryError as exc:  # pragma: no cover - tenacity reraise=True covers this
        raise exc.last_attempt.exception()  # type: ignore[misc]
    raise RuntimeError("unreachable")  # pragma: no cover


__all__ = ["transient_provider_retry", "with_retry"]
