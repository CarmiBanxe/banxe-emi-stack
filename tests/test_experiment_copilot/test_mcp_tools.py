"""
tests/test_experiment_copilot/test_mcp_tools.py
IL-CEC-01 | banxe-emi-stack

Tests for the 4 experiment MCP tools. All API calls are mocked via httpx.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestExperimentDesignTool:
    @pytest.mark.asyncio
    async def test_experiment_design_success(self):
        from banxe_mcp.server import experiment_design

        mock_response = {
            "id": "exp-2026-04-trans-test",
            "title": "Transaction Monitoring: reduce false positives",
            "scope": "transaction_monitoring",
            "status": "draft",
            "hypothesis": "By tuning velocity controls...",
            "kb_citations": ["eba-gl-2021-02"],
            "created_by": "analyst@banxe.com",
            "metrics_baseline": {"hit_rate_24h": 0.25},
            "metrics_target": {"hit_rate_24h": 0.35},
            "tags": ["transaction_monitoring"],
            "created_at": "2026-04-11T10:00:00",
            "updated_at": "2026-04-11T10:00:00",
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await experiment_design(
                query="reduce false positive rate",
                scope="transaction_monitoring",
                created_by="analyst@banxe.com",
            )
        assert "exp-2026-04-trans-test" in result
        assert "DRAFT" in result.upper() or "draft" in result

    @pytest.mark.asyncio
    async def test_experiment_design_api_error(self):
        from banxe_mcp.server import experiment_design
        import httpx

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            )
            result = await experiment_design(
                query="test",
                scope="transaction_monitoring",
                created_by="test@banxe.com",
            )
        assert "Error" in result


class TestExperimentListTool:
    @pytest.mark.asyncio
    async def test_experiment_list_all(self):
        from banxe_mcp.server import experiment_list

        mock_response = [
            {
                "id": "exp-001",
                "title": "Test Experiment",
                "scope": "transaction_monitoring",
                "status": "draft",
                "updated_at": "2026-04-11T10:00:00",
            }
        ]
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            result = await experiment_list()
        assert "exp-001" in result
        assert "Test Experiment" in result

    @pytest.mark.asyncio
    async def test_experiment_list_by_status(self):
        from banxe_mcp.server import experiment_list

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            await experiment_list(status="active")
        mock_get.assert_called_once()
        call_path = mock_get.call_args[0][0]
        assert "active" in call_path

    @pytest.mark.asyncio
    async def test_experiment_list_empty(self):
        from banxe_mcp.server import experiment_list

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = []
            result = await experiment_list()
        assert "0" in result or "no" in result.lower() or result.strip() != ""


class TestExperimentGetMetricsTool:
    @pytest.mark.asyncio
    async def test_experiment_get_metrics_success(self):
        from banxe_mcp.server import experiment_get_metrics

        mock_response = {
            "hit_rate_24h": 0.25,
            "false_positive_rate": 0.75,
            "sar_yield": 0.10,
            "cases_reviewed": 120,
            "period_days": 1,
        }
        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response
            result = await experiment_get_metrics(period_days=1)
        assert "25.0%" in result or "Hit Rate" in result

    @pytest.mark.asyncio
    async def test_experiment_get_metrics_api_error(self):
        from banxe_mcp.server import experiment_get_metrics
        import httpx

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            )
            result = await experiment_get_metrics()
        assert "Error" in result


class TestExperimentProposeChangeTool:
    @pytest.mark.asyncio
    async def test_experiment_propose_dry_run(self):
        from banxe_mcp.server import experiment_propose_change

        mock_response = {
            "experiment_id": "exp-001",
            "branch_name": "compliance/exp-exp-001",
            "pr_title": "[Compliance Experiment] Test",
            "pr_body": "## Compliance Experiment: Test\n\n...",
            "status": "pending",
            "pr_url": None,
            "issue_url": None,
            "hitl_checklist": {
                "ctio_reviewed": False,
                "compliance_officer_signoff": False,
                "backtest_results_reviewed": False,
                "rollback_plan_defined": False,
            },
            "files_changed": ["compliance-experiments/active/exp-001.yaml"],
        }
        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await experiment_propose_change(experiment_id="exp-001", dry_run=True)
        assert "compliance/exp-exp-001" in result or "exp-001" in result

    @pytest.mark.asyncio
    async def test_experiment_propose_api_error(self):
        from banxe_mcp.server import experiment_propose_change
        import httpx

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "422", request=MagicMock(), response=MagicMock(status_code=422)
            )
            result = await experiment_propose_change(experiment_id="exp-draft", dry_run=True)
        assert "Error" in result
