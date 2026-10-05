from __future__ import annotations

from collections.abc import Callable
from typing import ParamSpec, TypeVar

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential_jitter

P = ParamSpec("P")
T = TypeVar("T")


def is_transient(error: BaseException) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return True
    return isinstance(error, httpx.HTTPStatusError) and error.response.status_code in {
        429,
        500,
        502,
        503,
        504,
    }


def with_retries(max_retries: int) -> Callable[[Callable[P, T]], Callable[P, T]]:
    return retry(
        retry=retry_if_exception(is_transient),
        wait=wait_exponential_jitter(initial=1, max=60),
        stop=stop_after_attempt(max_retries + 1),
        reraise=True,
    )

