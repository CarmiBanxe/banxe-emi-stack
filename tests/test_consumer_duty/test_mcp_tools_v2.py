"""
tests/test_consumer_duty/test_mcp_tools_v2.py
Tests for consumer duty Phase 50 MCP tools.
IL-CDO-01 | Phase 50 | Sprint 35

≥15 tests covering:
- consumer_duty_assess_outcome
- consumer_duty_get_dashboard
- consumer_duty_detect_vulnerability
- consumer_duty_failing_products
- consumer_duty_export_board_report
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from banxe_mcp.server import (
    consumer_duty_assess_outcome,
    consumer_duty_detect_vulnerability,
    consumer_duty_export_board_report,
    consumer_duty_failing_products,
    consumer_duty_get_dashboard,
)
import httpx
import pytest

# ── consumer_duty_assess_outcome tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_assess_outcome_returns_assessment() -> None:
    """Test consumer_duty_assess_outcome returns assessment data."""
    mock_result = {
        "assessment_id": "asm_abc123",
        "customer_id": "c1",
        "outcome_type": "PRODUCTS_SERVICES",
        "score": "0.8",
        "status": "PASSED",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_assess_outcome("c1", "PRODUCTS_SERVICES", "0.8")
        data = json.loads(result)
        assert data["assessment_id"] == "asm_abc123"
        assert data["status"] == "PASSED"


@pytest.mark.asyncio
async def test_assess_outcome_failed_status() -> None:
    """Test consumer_duty_assess_outcome with failing score."""
    mock_result = {"status": "FAILED", "score": "0.5"}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_assess_outcome("c1", "PRICE_VALUE", "0.5")
        data = json.loads(result)
        assert data["status"] == "FAILED"


@pytest.mark.asyncio
async def test_assess_outcome_http_error() -> None:
    """Test consumer_duty_assess_outcome handles HTTP error."""
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError(
            "422", request=httpx.Request("POST", "http://test"), response=httpx.Response(422)
        ),
    ):
        result = await consumer_duty_assess_outcome("c1", "PRODUCTS_SERVICES", "0.8")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_assess_outcome_connect_error() -> None:
    """Test consumer_duty_assess_outcome handles connection error."""
    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await consumer_duty_assess_outcome("c1", "PRODUCTS_SERVICES", "0.8")
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"


# ── consumer_duty_get_dashboard tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_dashboard_returns_dashboard() -> None:
    """Test consumer_duty_get_dashboard returns dashboard data."""
    mock_result = {
        "generated_at": "2026-04-21T00:00:00",
        "total_failing_outcomes": 2,
        "outcome_areas": {},
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_get_dashboard()
        data = json.loads(result)
        assert "generated_at" in data
        assert data["total_failing_outcomes"] == 2


@pytest.mark.asyncio
async def test_get_dashboard_connect_error() -> None:
    """Test consumer_duty_get_dashboard handles connection error."""
    with patch("banxe_mcp.server._api_get", side_effect=httpx.ConnectError("refused")):
        result = await consumer_duty_get_dashboard()
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"


# ── consumer_duty_detect_vulnerability tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_detect_vulnerability_returns_alert() -> None:
    """Test consumer_duty_detect_vulnerability returns alert data."""
    mock_result = {
        "type": "VulnerabilityAlert",
        "alert_id": "vul_abc123",
        "vulnerability_flag": "LOW",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_detect_vulnerability("c1", "age_indicator")
        data = json.loads(result)
        assert data["type"] == "VulnerabilityAlert"


@pytest.mark.asyncio
async def test_detect_vulnerability_high_returns_hitl() -> None:
    """Test HIGH severity returns HITLProposal data."""
    mock_result = {
        "type": "HITLProposal",
        "action": "REVIEW_VULNERABILITY",
        "requires_approval_from": "CONSUMER_DUTY_OFFICER",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_detect_vulnerability("c1", "debt_restructure", "HIGH")
        data = json.loads(result)
        assert data["type"] == "HITLProposal"


@pytest.mark.asyncio
async def test_detect_vulnerability_http_error() -> None:
    """Test consumer_duty_detect_vulnerability handles HTTP error."""
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError(
            "500", request=httpx.Request("POST", "http://test"), response=httpx.Response(500)
        ),
    ):
        result = await consumer_duty_detect_vulnerability("c1", "age_indicator")
        data = json.loads(result)
        assert "error" in data


# ── consumer_duty_failing_products tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_failing_products_returns_list() -> None:
    """Test consumer_duty_failing_products returns list of failing products."""
    mock_result = [{"product_id": "p1", "intervention_type": "RESTRICT", "fair_value_score": "0.4"}]
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_failing_products()
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["intervention_type"] == "RESTRICT"


@pytest.mark.asyncio
async def test_failing_products_empty_list() -> None:
    """Test consumer_duty_failing_products returns empty list."""
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = []
        result = await consumer_duty_failing_products()
        data = json.loads(result)
        assert data == []


@pytest.mark.asyncio
async def test_failing_products_connect_error() -> None:
    """Test consumer_duty_failing_products handles connection error."""
    with patch("banxe_mcp.server._api_get", side_effect=httpx.ConnectError("refused")):
        result = await consumer_duty_failing_products()
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"


# ── consumer_duty_export_board_report tests ───────────────────────────────────


@pytest.mark.asyncio
async def test_export_board_report_returns_hitl() -> None:
    """Test consumer_duty_export_board_report returns HITLProposal data."""
    mock_result = {
        "action": "EXPORT_BOARD_REPORT",
        "requires_approval_from": "CFO",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consumer_duty_export_board_report("cfo_001")
        data = json.loads(result)
        assert data["action"] == "EXPORT_BOARD_REPORT"
        assert data["requires_approval_from"] == "CFO"


@pytest.mark.asyncio
async def test_export_board_report_connect_error() -> None:
    """Test consumer_duty_export_board_report handles connection error."""
    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await consumer_duty_export_board_report("cfo_001")
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"
