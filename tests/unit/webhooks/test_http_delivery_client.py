"""
test_http_delivery_client.py — HttpWebhookDeliveryClient tests (ADR-034 Step 4).

Uses httpx.MockTransport — no real network. Each test owns a transport that
returns a programmed response (or raises) for the single POST under test.
"""

from __future__ import annotations

import httpx

from services.webhooks.http_delivery_client import HttpWebhookDeliveryClient


def _client_with(transport: httpx.MockTransport) -> HttpWebhookDeliveryClient:
    async_client = httpx.AsyncClient(transport=transport)
    return HttpWebhookDeliveryClient(client=async_client)


async def test_deliver_2xx_returns_success() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = request.read().decode()
        return httpx.Response(200)

    client = _client_with(httpx.MockTransport(handler))
    res = await client.deliver("https://kc/hook", {"applicantId": "a1"}, 5.0)
    assert res.success is True
    assert res.status_code == 200
    assert res.error is None
    assert seen["url"] == "https://kc/hook"
    assert '"applicantId"' in seen["json"]


async def test_deliver_4xx_returns_failure_with_status() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(401))
    client = _client_with(transport)
    res = await client.deliver("https://x", {}, 5.0)
    assert res.success is False
    assert res.status_code == 401
    assert "http 401" in (res.error or "")


async def test_deliver_5xx_returns_failure_with_status() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(503))
    client = _client_with(transport)
    res = await client.deliver("https://x", {}, 5.0)
    assert res.success is False
    assert res.status_code == 503
    assert "http 503" in (res.error or "")


async def test_deliver_timeout_returns_failure_no_status() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("connect timeout")

    client = _client_with(httpx.MockTransport(handler))
    res = await client.deliver("https://x", {}, 0.1)
    assert res.success is False
    assert res.status_code is None
    assert "ConnectTimeout" in (res.error or "")


async def test_deliver_network_exception_returns_failure_no_status() -> None:
    def handler(_req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure")

    client = _client_with(httpx.MockTransport(handler))
    res = await client.deliver("https://x", {}, 5.0)
    assert res.success is False
    assert res.status_code is None
    assert "ConnectError" in (res.error or "")
    assert "dns failure" in (res.error or "")
