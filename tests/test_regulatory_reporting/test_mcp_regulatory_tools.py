"""
tests/test_regulatory_reporting/test_mcp_regulatory_tools.py
IL-RRA-01 | Phase 14

Tests for 5 MCP regulatory tools:
  report_generate, report_validate, report_schedule, report_audit_log, report_list_templates
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from banxe_mcp.server import (
    report_audit_log,
    report_generate,
    report_list_templates,
    report_schedule,
    report_validate,
)
import httpx
import pytest

# ── report_generate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_generate_success() -> None:
    mock_result = {
        "report_id": "rep-001",
        "report_type": "FIN060",
        "status": "VALIDATED",
        "validation_errors": [],
        "generated_at": "2025-01-31T12:00:00+00:00",
        "xml_content": "<FIN060Return/>",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await report_generate(
            report_type="FIN060",
            entity_id="FRN123456",
            entity_name="Banxe EMI Ltd",
            period_start="2025-01-01",
            period_end="2025-01-31",
            actor="compliance@banxe.com",
        )
    data = json.loads(result)
    assert data["report_id"] == "rep-001"
    assert data["status"] == "VALIDATED"


@pytest.mark.asyncio
async def test_report_generate_with_financial_data() -> None:
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = {"report_id": "rep-002", "status": "VALIDATED", "validation_errors": []}
        result = await report_generate(
            report_type="FIN060",
            entity_id="FRN123456",
            entity_name="Banxe EMI Ltd",
            period_start="2025-01-01",
            period_end="2025-01-31",
            actor="actor1",
            financial_data='{"total_client_assets": "500000.00"}',
        )
    data = json.loads(result)
    assert "report_id" in data
    # Verify financial_data was passed to API
    call_args = mock.call_args[0]
    assert call_args[1]["financial_data"]["total_client_assets"] == "500000.00"


@pytest.mark.asyncio
async def test_report_generate_http_error() -> None:
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError("422", request=None, response=AsyncMock(status_code=422)),
    ):
        result = await report_generate(
            report_type="UNKNOWN",
            entity_id="X",
            entity_name="X",
            period_start="2025-01-01",
            period_end="2025-01-31",
            actor="actor1",
        )
    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_report_generate_invalid_financial_data_json() -> None:
    result = await report_generate(
        report_type="FIN060",
        entity_id="FRN123456",
        entity_name="Banxe EMI Ltd",
        period_start="2025-01-01",
        period_end="2025-01-31",
        actor="actor1",
        financial_data="{invalid json",
    )
    data = json.loads(result)
    assert "error" in data


# ── report_validate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_validate_valid_xml() -> None:
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = {"status": "VALIDATED", "validation_errors": [], "report_id": "rep-003"}
        result = await report_validate("FIN060", "<FIN060Return/>")
    data = json.loads(result)
    assert data["is_valid"] is True
    assert data["validation_errors"] == []


@pytest.mark.asyncio
async def test_report_validate_invalid_xml() -> None:
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "status": "FAILED",
            "validation_errors": ["Missing <FirmRef>"],
            "report_id": "rep-004",
        }
        result = await report_validate("FIN060", "<bad/>")
    data = json.loads(result)
    assert data["is_valid"] is False


# ── report_schedule ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_schedule_monthly() -> None:
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "schedule_id": "sched-001",
            "report_type": "FIN060",
            "entity_id": "FRN123456",
            "frequency": "MONTHLY",
            "next_run_at": "2025-02-01T06:00:00+00:00",
            "is_active": True,
        }
        result = await report_schedule(
            report_type="FIN060",
            entity_id="FRN123456",
            frequency="MONTHLY",
            actor="admin@banxe.com",
        )
    data = json.loads(result)
    assert data["schedule_id"] == "sched-001"
    assert data["frequency"] == "MONTHLY"


@pytest.mark.asyncio
async def test_report_schedule_http_error() -> None:
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError("502", request=None, response=AsyncMock(status_code=502)),
    ):
        result = await report_schedule(
            report_type="FIN060",
            entity_id="FRN123456",
            frequency="MONTHLY",
            actor="admin@banxe.com",
        )
    data = json.loads(result)
    assert "error" in data


# ── report_audit_log ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_audit_log_returns_entries() -> None:
    mock_response = {
        "count": 2,
        "entries": [
            {"id": "a1", "event_type": "report.generated", "report_type": "FIN060"},
            {"id": "a2", "event_type": "report.validated", "report_type": "FIN060"},
        ],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_response
        result = await report_audit_log(entity_id="FRN123456", report_type="FIN060", days=30)
    data = json.loads(result)
    assert data["count"] == 2
    assert len(data["entries"]) == 2


@pytest.mark.asyncio
async def test_report_audit_log_empty_params() -> None:
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = {"count": 0, "entries": []}
        result = await report_audit_log()
    data = json.loads(result)
    assert data["count"] == 0
    # Verify no entity_id/report_type params sent when empty
    call_kwargs = mock.call_args[1] if mock.call_args[1] else {}
    params = call_kwargs.get("params", mock.call_args[0][1] if len(mock.call_args[0]) > 1 else {})
    assert "entity_id" not in params
    assert "report_type" not in params


@pytest.mark.asyncio
async def test_report_audit_log_http_error() -> None:
    with patch(
        "banxe_mcp.server._api_get",
        side_effect=httpx.HTTPStatusError("500", request=None, response=AsyncMock(status_code=500)),
    ):
        result = await report_audit_log()
    data = json.loads(result)
    assert "error" in data


# ── report_list_templates ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_report_list_templates_six_types() -> None:
    mock_response = {
        "count": 6,
        "templates": [
            {"report_type": "FIN060", "sla_days": 15, "regulator": "FCA_REGDATA"},
            {"report_type": "FIN071", "sla_days": 30, "regulator": "FCA_REGDATA"},
            {"report_type": "FSA076", "sla_days": 30, "regulator": "FCA_REGDATA"},
            {"report_type": "SAR_BATCH", "sla_days": 1, "regulator": "NCA_GATEWAY"},
            {"report_type": "BOE_FORM_BT", "sla_days": 25, "regulator": "BOE_STATISTICAL"},
            {"report_type": "ACPR_EMI", "sla_days": 45, "regulator": "ACPR_PORTAL"},
        ],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_response
        result = await report_list_templates()
    data = json.loads(result)
    assert data["count"] == 6
    types = [t["report_type"] for t in data["templates"]]
    assert "FIN060" in types
    assert "ACPR_EMI" in types


@pytest.mark.asyncio
async def test_report_list_templates_http_error() -> None:
    with patch(
        "banxe_mcp.server._api_get",
        side_effect=httpx.HTTPStatusError("503", request=None, response=AsyncMock(status_code=503)),
    ):
        result = await report_list_templates()
    data = json.loads(result)
    assert "error" in data
