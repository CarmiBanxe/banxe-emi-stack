"""Tests for FOS Escalation MCP tools (IL-FOS-01).

Pattern: mock _api_get/_api_post, not httpx directly.
Phase 56A | Sprint 41
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── fos_prepare_case ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fos_prepare_case_success() -> None:
    from banxe_mcp.server import fos_prepare_case

    mock_result = {
        "case_id": "fos_abc12345",
        "complaint_id": "CMP001",
        "status": "READY",
        "weeks_since_complaint": 7,
        "prepared_at": "2026-04-27T10:00:00+00:00",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await fos_prepare_case("CMP001", "CUST001", 7)

    data = json.loads(result)
    assert data["case_id"] == "fos_abc12345"
    assert data["status"] == "READY"


@pytest.mark.asyncio
async def test_fos_prepare_case_returns_string() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_001", "status": "PREPARING"}
        result = await fos_prepare_case("CMP001", "CUST001", 3)

    assert isinstance(result, str)
    assert json.loads(result)  # valid JSON


@pytest.mark.asyncio
async def test_fos_prepare_case_preparing_status_at_week3() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "case_id": "fos_001",
            "status": "PREPARING",
            "weeks_since_complaint": 3,
        }
        result = await fos_prepare_case("CMP001", "CUST001", 3)

    data = json.loads(result)
    assert data["status"] == "PREPARING"


@pytest.mark.asyncio
async def test_fos_prepare_case_ready_status_at_week6() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "case_id": "fos_002",
            "status": "READY",
            "weeks_since_complaint": 6,
        }
        result = await fos_prepare_case("CMP002", "CUST002", 6)

    data = json.loads(result)
    assert data["status"] == "READY"


@pytest.mark.asyncio
async def test_fos_prepare_case_http_error() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 422
        mock_post.side_effect = httpx.HTTPStatusError(
            "Unprocessable", request=AsyncMock(), response=mock_resp
        )
        result = await fos_prepare_case("CMP001", "CUST001", -1)

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 422


@pytest.mark.asyncio
async def test_fos_prepare_case_passes_firm_decision() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_003", "status": "READY"}
        await fos_prepare_case("CMP003", "CUST003", 6, firm_decision="upheld")

    call_kwargs = mock_post.call_args[0][1]
    assert call_kwargs["firm_decision"] == "upheld"


@pytest.mark.asyncio
async def test_fos_prepare_case_default_firm_decision() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_004", "status": "PREPARING"}
        await fos_prepare_case("CMP004", "CUST004", 4)

    call_kwargs = mock_post.call_args[0][1]
    assert call_kwargs["firm_decision"] == "not_upheld"


@pytest.mark.asyncio
async def test_fos_prepare_case_posts_to_correct_endpoint() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_005"}
        await fos_prepare_case("CMP_TARGET", "CUST001", 5)

    endpoint = mock_post.call_args[0][0]
    assert "CMP_TARGET" in endpoint
    assert endpoint.startswith("/v1/fos/prepare/")


# ── fos_list_cases ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fos_list_cases_success() -> None:
    from banxe_mcp.server import fos_list_cases

    mock_result = {
        "total": 3,
        "week6_flagged": 1,
        "cases": [
            {"case_id": "fos_001", "status": "READY"},
            {"case_id": "fos_002", "status": "PREPARING"},
        ],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await fos_list_cases()

    data = json.loads(result)
    assert data["total"] == 3
    assert data["week6_flagged"] == 1
    assert len(data["cases"]) == 2


@pytest.mark.asyncio
async def test_fos_list_cases_returns_string() -> None:
    from banxe_mcp.server import fos_list_cases

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"total": 0, "week6_flagged": 0, "cases": []}
        result = await fos_list_cases()

    assert isinstance(result, str)
    assert json.loads(result)  # valid JSON


@pytest.mark.asyncio
async def test_fos_list_cases_empty_list() -> None:
    from banxe_mcp.server import fos_list_cases

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"total": 0, "week6_flagged": 0, "cases": []}
        result = await fos_list_cases()

    data = json.loads(result)
    assert data["total"] == 0
    assert data["cases"] == []


@pytest.mark.asyncio
async def test_fos_list_cases_http_error() -> None:
    from banxe_mcp.server import fos_list_cases

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 500
        mock_get.side_effect = httpx.HTTPStatusError(
            "Server Error", request=AsyncMock(), response=mock_resp
        )
        result = await fos_list_cases()

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 500


@pytest.mark.asyncio
async def test_fos_list_cases_gets_correct_endpoint() -> None:
    from banxe_mcp.server import fos_list_cases

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"total": 0, "week6_flagged": 0, "cases": []}
        await fos_list_cases()

    endpoint = mock_get.call_args[0][0]
    assert endpoint == "/v1/fos/cases"


@pytest.mark.asyncio
async def test_fos_prepare_case_week8_ready() -> None:
    """Week 8 (at deadline) is also READY."""
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {
            "case_id": "fos_w8",
            "status": "READY",
            "weeks_since_complaint": 8,
        }
        result = await fos_prepare_case("CMP_W8", "CUST001", 8)

    data = json.loads(result)
    assert data["status"] == "READY"
    assert data["weeks_since_complaint"] == 8


@pytest.mark.asyncio
async def test_fos_list_cases_week6_flagged_count() -> None:
    from banxe_mcp.server import fos_list_cases

    mock_result = {
        "total": 5,
        "week6_flagged": 3,
        "cases": [],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await fos_list_cases()

    data = json.loads(result)
    assert data["week6_flagged"] == 3


@pytest.mark.asyncio
async def test_fos_prepare_case_passes_weeks_elapsed() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_w5", "status": "PREPARING"}
        await fos_prepare_case("CMP_W5", "CUST001", 5)

    body = mock_post.call_args[0][1]
    assert body["weeks_elapsed"] == 5


@pytest.mark.asyncio
async def test_fos_prepare_case_passes_customer_id() -> None:
    from banxe_mcp.server import fos_prepare_case

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"case_id": "fos_c2", "status": "PREPARING"}
        await fos_prepare_case("CMP001", "CUST_TARGET_ID", 4)

    body = mock_post.call_args[0][1]
    assert body["customer_id"] == "CUST_TARGET_ID"
