"""Tests for Customer Lifecycle MCP tools (IL-LCY-01).

Pattern: mock _api_get/_api_post, not httpx directly.
Phase 56D | Sprint 41
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── lifecycle_transition ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_transition_success() -> None:
    from banxe_mcp.server import lifecycle_transition

    mock_result = {
        "customer_id": "CUST001",
        "from_state": "prospect",
        "to_state": "onboarding",
        "event": "submit_application",
        "transitioned_at": "2026-04-27T10:00:00+00:00",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await lifecycle_transition("CUST001", "submit_application")

    data = json.loads(result)
    assert data["to_state"] == "onboarding"
    assert data["from_state"] == "prospect"


@pytest.mark.asyncio
async def test_lifecycle_transition_returns_string() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"customer_id": "CUST001", "to_state": "onboarding"}
        result = await lifecycle_transition("CUST001", "submit_application")

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_lifecycle_transition_blocked_jurisdiction_error() -> None:
    """I-02: RU blocked on submit_application."""
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_post.side_effect = httpx.HTTPStatusError(
            "Blocked jurisdiction", request=AsyncMock(), response=mock_resp
        )
        result = await lifecycle_transition("CUST_RU", "submit_application", country="RU")

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 400


@pytest.mark.asyncio
async def test_lifecycle_transition_invalid_transition_error() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 422
        mock_post.side_effect = httpx.HTTPStatusError(
            "Invalid transition", request=AsyncMock(), response=mock_resp
        )
        result = await lifecycle_transition("CUST001", "activate")

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 422


@pytest.mark.asyncio
async def test_lifecycle_transition_default_country_gb() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"customer_id": "CUST001", "to_state": "onboarding"}
        await lifecycle_transition("CUST001", "submit_application")

    body = mock_post.call_args[0][1]
    assert body["country"] == "GB"


@pytest.mark.asyncio
async def test_lifecycle_transition_posts_to_correct_endpoint() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"customer_id": "CUST_T", "to_state": "onboarding"}
        await lifecycle_transition("CUST_T", "submit_application")

    endpoint = mock_post.call_args[0][0]
    assert "CUST_T" in endpoint
    assert "transition" in endpoint


@pytest.mark.asyncio
async def test_lifecycle_transition_custom_country() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"customer_id": "CUST_DE", "to_state": "onboarding"}
        await lifecycle_transition("CUST_DE", "submit_application", country="DE")

    body = mock_post.call_args[0][1]
    assert body["country"] == "DE"


@pytest.mark.asyncio
async def test_lifecycle_transition_passes_event() -> None:
    from banxe_mcp.server import lifecycle_transition

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"customer_id": "C1", "to_state": "active"}
        await lifecycle_transition("C1", "activate")

    body = mock_post.call_args[0][1]
    assert body["event"] == "activate"


# ── lifecycle_list_dormant ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_lifecycle_list_dormant_success() -> None:
    from banxe_mcp.server import lifecycle_list_dormant

    mock_result = {
        "dormant_count": 3,
        "customer_ids": ["CUST001", "CUST002", "CUST003"],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await lifecycle_list_dormant()

    data = json.loads(result)
    assert data["dormant_count"] == 3
    assert len(data["customer_ids"]) == 3


@pytest.mark.asyncio
async def test_lifecycle_list_dormant_returns_string() -> None:
    from banxe_mcp.server import lifecycle_list_dormant

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"dormant_count": 0, "customer_ids": []}
        result = await lifecycle_list_dormant()

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_lifecycle_list_dormant_empty() -> None:
    from banxe_mcp.server import lifecycle_list_dormant

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"dormant_count": 0, "customer_ids": []}
        result = await lifecycle_list_dormant()

    data = json.loads(result)
    assert data["dormant_count"] == 0
    assert data["customer_ids"] == []


@pytest.mark.asyncio
async def test_lifecycle_list_dormant_http_error() -> None:
    from banxe_mcp.server import lifecycle_list_dormant

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 503
        mock_get.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=AsyncMock(), response=mock_resp
        )
        result = await lifecycle_list_dormant()

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 503


@pytest.mark.asyncio
async def test_lifecycle_list_dormant_gets_correct_endpoint() -> None:
    from banxe_mcp.server import lifecycle_list_dormant

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"dormant_count": 0, "customer_ids": []}
        await lifecycle_list_dormant()

    endpoint = mock_get.call_args[0][0]
    assert endpoint == "/v1/lifecycle/dormant"
