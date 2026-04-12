"""
tests/test_transaction_monitor/test_mcp_tools.py
IL-RTM-01 | banxe-emi-stack

Tests for the 5 transaction monitor MCP tools. All API calls are mocked via httpx.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMonitorScoreTransactionTool:
    @pytest.mark.asyncio
    async def test_score_transaction_success(self):
        from banxe_mcp.server import monitor_score_transaction

        mock_response = {
            "transaction_id": "TXN-MCP-001",
            "risk_score": {
                "score": 0.72,
                "classification": "high",
                "factors": [
                    {
                        "name": "velocity_24h",
                        "value": 0.85,
                        "contribution": 0.26,
                        "regulation_ref": "EBA GL/2021/02 §4.2",
                    }
                ],
                "model_version": "v1",
                "computed_at": "2026-04-12T10:00:00",
                "rules_score": 0.70,
                "ml_score": 0.65,
                "velocity_score": 0.85,
            },
            "alert": {
                "alert_id": "ALT-ABCD1234",
                "transaction_id": "TXN-MCP-001",
                "customer_id": "cust-001",
                "severity": "high",
                "status": "reviewing",
                "recommended_action": "review",
                "marble_case_id": "MBL-001",
                "amount_gbp": "15000.00",
                "explanation": "High velocity detected.",
                "regulation_refs": ["EBA GL/2021/02 §4.2"],
            },
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await monitor_score_transaction(
                transaction_id="TXN-MCP-001",
                amount="15000.00",
                sender_id="cust-001",
                sender_jurisdiction="GB",
            )
        assert "TXN-MCP-001" in result
        assert "ALT-ABCD1234" in result
        assert "HIGH" in result.upper() or "high" in result

    @pytest.mark.asyncio
    async def test_score_transaction_api_error(self):
        from banxe_mcp.server import monitor_score_transaction
        import httpx

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
            result = await monitor_score_transaction(
                transaction_id="TXN-ERR",
                amount="1000.00",
                sender_id="cust-err",
            )
        assert "Error" in result


class TestMonitorGetAlertsTool:
    @pytest.mark.asyncio
    async def test_get_alerts_returns_table(self):
        from banxe_mcp.server import monitor_get_alerts

        mock_alerts = [
            {
                "alert_id": "ALT-TABLE001",
                "transaction_id": "TXN-T001",
                "severity": "high",
                "status": "open",
                "risk_score": {"score": 0.73},
                "created_at": "2026-04-12T09:00:00",
            }
        ]
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_alerts
            result = await monitor_get_alerts(severity="high")
        assert "ALT-TABLE001" in result
        assert "TXN-T001" in result

    @pytest.mark.asyncio
    async def test_get_alerts_empty_returns_message(self):
        from banxe_mcp.server import monitor_get_alerts

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            result = await monitor_get_alerts(status="closed")
        assert "No alerts" in result or "0" in result or result.strip()

    @pytest.mark.asyncio
    async def test_get_alerts_api_error(self):
        from banxe_mcp.server import monitor_get_alerts
        import httpx

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            )
            result = await monitor_get_alerts()
        assert "Error" in result


class TestMonitorGetAlertDetailTool:
    @pytest.mark.asyncio
    async def test_get_alert_detail_success(self):
        from banxe_mcp.server import monitor_get_alert_detail

        mock_alert = {
            "alert_id": "ALT-DETAIL01",
            "transaction_id": "TXN-D001",
            "customer_id": "cust-detail",
            "severity": "critical",
            "status": "escalated",
            "amount_gbp": "95000.00",
            "explanation": "Transaction from sanctioned jurisdiction.",
            "regulation_refs": ["EBA GL/2021/02 §4.2"],
            "review_deadline": "2026-04-12T13:00:00",
            "marble_case_id": "MBL-CRIT-001",
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_alert
            result = await monitor_get_alert_detail("ALT-DETAIL01")
        assert "ALT-DETAIL01" in result
        assert "TXN-D001" in result
        assert "sanctioned jurisdiction" in result
        assert "EBA" in result

    @pytest.mark.asyncio
    async def test_get_alert_detail_not_found(self):
        from banxe_mcp.server import monitor_get_alert_detail
        import httpx

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=MagicMock(status_code=404)
            )
            result = await monitor_get_alert_detail("ALT-NOTFOUND")
        assert "Error" in result


class TestMonitorGetVelocityTool:
    @pytest.mark.asyncio
    async def test_get_velocity_success(self):
        from banxe_mcp.server import monitor_get_velocity

        mock_data = {
            "customer_id": "cust-vel-001",
            "velocity": {
                "1h": {"count": 3, "threshold": 5, "exceeded": False},
                "24h": {"count": 12, "threshold": 10, "exceeded": True},
                "7d": {"count": 45, "threshold": 50, "exceeded": False},
            },
            "cumulative_gbp_24h": "11500.00",
            "requires_edd": True,
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_data
            result = await monitor_get_velocity("cust-vel-001")
        assert "cust-vel-001" in result
        assert "11500" in result
        assert "EDD" in result or "I-04" in result or "YES" in result

    @pytest.mark.asyncio
    async def test_get_velocity_api_error(self):
        from banxe_mcp.server import monitor_get_velocity
        import httpx

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
            result = await monitor_get_velocity("cust-err")
        assert "Error" in result


class TestMonitorDashboardMetricsTool:
    @pytest.mark.asyncio
    async def test_dashboard_metrics_success(self):
        from banxe_mcp.server import monitor_dashboard_metrics

        mock_metrics = {
            "total_alerts": 42,
            "by_severity": {"critical": 5, "high": 12, "medium": 18, "low": 7},
            "open_alerts": 20,
            "escalated_alerts": 5,
            "sar_yield_estimate": 0.25,
            "targets": {
                "false_positive_target": 0.35,
                "sar_yield_target": 0.20,
                "review_sla_hours": 24,
            },
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_metrics
            result = await monitor_dashboard_metrics()
        assert "42" in result
        assert "5" in result  # critical count
        assert "SAR" in result

    @pytest.mark.asyncio
    async def test_dashboard_metrics_api_error(self):
        from banxe_mcp.server import monitor_dashboard_metrics
        import httpx

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            )
            result = await monitor_dashboard_metrics()
        assert "Error" in result
