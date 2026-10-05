from __future__ import annotations

import httpx
import pytest

from ndd_corpus.utils.http import NcbiClient


def test_ncbi_client_retries_transient_network_error() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, json={"ok": True})

    with NcbiClient(
        email="owner@example.org",
        tool="test",
        max_retries=2,
        requests_per_second=10_000,
        transport=httpx.MockTransport(handler),
    ) as client:
        response = client.get("https://example.test/api")

    assert response.json() == {"ok": True}
    assert attempts == 2


def test_ncbi_client_retries_429_without_disclosing_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"ok": True})

    with NcbiClient(
        email="owner@example.org",
        tool="test",
        api_key="secret-key",
        max_retries=1,
        requests_per_second=10_000,
        transport=httpx.MockTransport(handler),
    ) as client:
        client.get("https://example.test/api")

    assert len(requests) == 2
    assert "secret-key" not in repr(client)


def test_ncbi_error_message_redacts_api_key() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(500))
    with NcbiClient(
        email="owner@example.org",
        tool="test",
        api_key="secret-key",
        max_retries=0,
        requests_per_second=10_000,
        transport=transport,
    ) as client, pytest.raises(RuntimeError) as captured:
        client.get("https://example.test/api")

    assert "secret-key" not in str(captured.value)
