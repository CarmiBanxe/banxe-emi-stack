"""
tests/test_support/test_mcp_support_tools.py — MCP Support Tool Tests
IL-CSB-01 | #117 | banxe-emi-stack

Tests for 4 support MCP tools in banxe_mcp/server.py:
  support_create_ticket, support_get_metrics, support_check_sla, support_route_ticket

All API calls mocked via _api_get / _api_post patches.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

# ─── support_create_ticket ────────────────────────────────────────────────────


class TestSupportCreateTicketTool:
    @pytest.mark.asyncio
    async def test_create_ticket_returns_ticket_json(self):
        from banxe_mcp.server import support_create_ticket

        mock_response = {
            "id": "t-abc-123",
            "customer_id": "cust-001",
            "subject": "Payment stuck",
            "category": "PAYMENT",
            "priority": "HIGH",
            "status": "IN_PROGRESS",
            "auto_resolved": False,
            "is_formal_complaint": False,
            "sla_deadline": "2026-04-16T10:00:00+00:00",
            "assigned_to": "payments-support",
            "channel": "API",
            "created_at": "2026-04-16T06:00:00+00:00",
            "resolved_at": None,
            "resolution_summary": "",
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_create_ticket(
                "cust-001", "Payment stuck", "My FPS payment is stuck since yesterday"
            )
            data = json.loads(result)
            assert data["id"] == "t-abc-123"
            assert data["category"] == "PAYMENT"
            assert data["priority"] == "HIGH"
            assert data["auto_resolved"] is False

    @pytest.mark.asyncio
    async def test_create_ticket_auto_resolved_field_present(self):
        from banxe_mcp.server import support_create_ticket

        mock_response = {
            "id": "t-faq-001",
            "customer_id": "cust-002",
            "subject": "What are the fees",
            "category": "GENERAL",
            "priority": "LOW",
            "status": "RESOLVED",
            "auto_resolved": True,
            "is_formal_complaint": False,
            "sla_deadline": "2026-04-19T06:00:00+00:00",
            "assigned_to": "general-support",
            "channel": "WEB",
            "created_at": "2026-04-16T06:00:00+00:00",
            "resolved_at": "2026-04-16T06:00:01+00:00",
            "resolution_summary": "Auto-resolved by FAQ bot (confidence=0.92)",
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_create_ticket(
                "cust-002", "What are the fees?", "How much do you charge for FX?", "WEB"
            )
            data = json.loads(result)
            assert data["auto_resolved"] is True
            assert "confidence=0.92" in data["resolution_summary"]

    @pytest.mark.asyncio
    async def test_create_ticket_http_error_returns_error_json(self):
        from banxe_mcp.server import support_create_ticket

        mock_resp = MagicMock()
        mock_resp.status_code = 422
        with patch(
            "banxe_mcp.server._api_post",
            side_effect=httpx.HTTPStatusError("422", request=MagicMock(), response=mock_resp),
        ):
            result = await support_create_ticket("c", "Hi", "Body text here please")
            data = json.loads(result)
            assert "error" in data


# ─── support_get_metrics ──────────────────────────────────────────────────────


class TestSupportGetMetricsTool:
    @pytest.mark.asyncio
    async def test_get_metrics_returns_csat_nps(self):
        from banxe_mcp.server import support_get_metrics

        mock_response = {
            "period_days": 30,
            "total_responses": 42,
            "avg_csat": 4.2,
            "avg_nps": 7.1,
            "nps_score": 35.7,
            "nps_promoters": 18,
            "nps_detractors": 3,
            "nps_passives": 21,
            "by_category": {"PAYMENT": 4.5, "GENERAL": 4.0},
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_get_metrics(30)
            data = json.loads(result)
            assert data["avg_csat"] == 4.2
            assert data["nps_score"] == 35.7
            assert data["total_responses"] == 42

    @pytest.mark.asyncio
    async def test_get_metrics_empty_period(self):
        from banxe_mcp.server import support_get_metrics

        mock_response = {
            "period_days": 7,
            "total_responses": 0,
            "avg_csat": None,
            "avg_nps": None,
            "nps_score": None,
            "nps_promoters": 0,
            "nps_detractors": 0,
            "nps_passives": 0,
            "by_category": {},
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_get_metrics(7)
            data = json.loads(result)
            assert data["total_responses"] == 0
            assert data["avg_csat"] is None

    @pytest.mark.asyncio
    async def test_get_metrics_http_error_returns_error_json(self):
        from banxe_mcp.server import support_get_metrics

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp),
        ):
            result = await support_get_metrics()
            data = json.loads(result)
            assert "error" in data


# ─── support_check_sla ────────────────────────────────────────────────────────


class TestSupportCheckSlaTool:
    @pytest.mark.asyncio
    async def test_check_sla_not_breached(self):
        from banxe_mcp.server import support_check_sla

        future = (datetime.now(UTC) + timedelta(hours=3)).isoformat()
        mock_response = {
            "id": "t-sla-001",
            "status": "IN_PROGRESS",
            "sla_deadline": future,
            "priority": "HIGH",
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_check_sla("t-sla-001")
            data = json.loads(result)
            assert data["is_sla_breached"] is False
            assert data["status"] == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_check_sla_breached_when_deadline_past(self):
        from banxe_mcp.server import support_check_sla

        past = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        mock_response = {
            "id": "t-sla-002",
            "status": "IN_PROGRESS",
            "sla_deadline": past,
            "priority": "CRITICAL",
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_check_sla("t-sla-002")
            data = json.loads(result)
            assert data["is_sla_breached"] is True

    @pytest.mark.asyncio
    async def test_check_sla_404_returns_error_json(self):
        from banxe_mcp.server import support_check_sla

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_resp),
        ):
            result = await support_check_sla("nonexistent-id")
            data = json.loads(result)
            assert "error" in data


# ─── support_route_ticket ─────────────────────────────────────────────────────


class TestSupportRouteTicketTool:
    @pytest.mark.asyncio
    async def test_route_ticket_fraud_returns_critical(self):
        from banxe_mcp.server import support_route_ticket

        # API ticket response — tool maps this to a routing summary
        mock_response = {
            "id": "t-route-001",
            "category": "FRAUD",
            "priority": "CRITICAL",
            "assigned_to": "fraud-team",
            "status": "IN_PROGRESS",
            "sla_deadline": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "auto_resolved": False,
            "is_formal_complaint": False,
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_route_ticket(
                "cust-001",
                "Unauthorized transaction",
                "I did not authorise this payment and suspect fraud",
            )
            data = json.loads(result)
            # Tool returns routing summary (different keys from ticket response)
            assert data["category"] == "FRAUD"
            assert data["priority"] == "CRITICAL"
            assert data["assigned_to"] == "fraud-team"
            assert data["sla_hours"] == 1  # CRITICAL SLA

    @pytest.mark.asyncio
    async def test_route_ticket_general_faq_auto_resolvable(self):
        from banxe_mcp.server import support_route_ticket

        mock_response = {
            "id": "t-route-002",
            "category": "GENERAL",
            "priority": "LOW",
            "assigned_to": "general-support",
            "status": "RESOLVED",
            "sla_deadline": (datetime.now(UTC) + timedelta(hours=72)).isoformat(),
            "auto_resolved": True,
            "is_formal_complaint": False,
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
            mock.return_value = mock_response
            result = await support_route_ticket(
                "cust-002",
                "What is the fee for FX transfers?",
                "How much does a SEPA transfer cost?",
            )
            data = json.loads(result)
            assert data["category"] == "GENERAL"
            assert data["auto_resolvable"] is True  # tool maps auto_resolved → auto_resolvable
            assert data["sla_hours"] == 72  # LOW SLA

    @pytest.mark.asyncio
    async def test_route_ticket_http_error_returns_error_json(self):
        from banxe_mcp.server import support_route_ticket

        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with patch(
            "banxe_mcp.server._api_post",
            side_effect=httpx.HTTPStatusError("500", request=MagicMock(), response=mock_resp),
        ):
            result = await support_route_ticket("c", "Subject here", "Body text here please")
            data = json.loads(result)
            assert "error" in data
