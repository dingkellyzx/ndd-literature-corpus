from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx


def sha256_file(path: str | Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: str | Path, content: bytes) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return destination


class RateLimiter:
    def __init__(self, requests_per_second: float):
        self.interval = 1.0 / requests_per_second
        self._next_request = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self._next_request - now
            if delay > 0:
                time.sleep(delay)
            self._next_request = max(now, self._next_request) + self.interval


class NcbiClient:
    """Small NCBI HTTP client with identification, throttling, and retries."""

    def __init__(
        self,
        *,
        email: str,
        tool: str,
        api_key: str | None = None,
        timeout: float = 60.0,
        max_retries: int = 8,
        requests_per_second: float = 2.5,
        transport: httpx.BaseTransport | None = None,
    ):
        if not email:
            raise ValueError("NCBI email is required")
        self.email = email
        self.tool = tool
        self._api_key = api_key
        self.max_retries = max_retries
        self.rate_limiter = RateLimiter(requests_per_second)
        self.client = httpx.Client(timeout=timeout, transport=transport, follow_redirects=True)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> NcbiClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> httpx.Response:
        request_values: dict[str, Any] = dict(params or data or {})
        request_values.update({"email": self.email, "tool": self.tool})
        if self._api_key:
            request_values["api_key"] = self._api_key
        for attempt in range(self.max_retries + 1):
            self.rate_limiter.wait()
            response = self.client.request(
                method,
                url,
                params=request_values if params is not None else None,
                data=request_values if data is not None else None,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            if attempt == self.max_retries:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            delay = float(retry_after) if retry_after else min(2**attempt, 60)
            time.sleep(delay)
        raise RuntimeError("unreachable retry loop")

    def get(self, url: str, *, params: Mapping[str, Any] | None = None) -> httpx.Response:
        return self.request("GET", url, params=params or {})

    def post(self, url: str, *, data: Mapping[str, Any] | None = None) -> httpx.Response:
        return self.request("POST", url, data=data or {})

