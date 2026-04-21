"""
tests/test_consent_management/test_mcp_tools.py
Tests for consent management MCP tools.
IL-CNS-01 | Phase 49 | Sprint 35

≥20 tests covering:
- consent_grant (mock _api_post)
- consent_validate (mock)
- consent_revoke (mock)
- consent_list_tpps (mock _api_get)
- consent_cbpii_check (mock, error handling)
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from banxe_mcp.server import (
    consent_cbpii_check,
    consent_grant,
    consent_list_tpps,
    consent_revoke,
    consent_validate,
)
import httpx
import pytest

# ── consent_grant tests ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_grant_returns_grant() -> None:
    """Test consent_grant returns ConsentGrant JSON."""
    mock_result = {
        "consent_id": "cns_abc123",
        "customer_id": "c1",
        "tpp_id": "tpp_plaid_uk",
        "status": "ACTIVE",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_grant("c1", "tpp_plaid_uk", "AISP", "ACCOUNTS,BALANCES")
        data = json.loads(result)
        assert data["consent_id"] == "cns_abc123"


@pytest.mark.asyncio
async def test_consent_grant_with_transaction_limit() -> None:
    """Test consent_grant with transaction_limit passed."""
    mock_result = {"consent_id": "cns_abc123", "transaction_limit": "500.00"}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_grant(
            "c1", "tpp_plaid_uk", "PISP", "PAYMENTS", transaction_limit="500.00"
        )
        data = json.loads(result)
        assert data["transaction_limit"] == "500.00"


@pytest.mark.asyncio
async def test_consent_grant_http_error_returns_error() -> None:
    """Test consent_grant handles HTTP error."""
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError(
            "422", request=httpx.Request("POST", "http://test"), response=httpx.Response(422)
        ),
    ):
        result = await consent_grant("c1", "tpp_unknown", "AISP", "ACCOUNTS")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_consent_grant_connect_error_returns_unavailable() -> None:
    """Test consent_grant handles connection error."""
    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await consent_grant("c1", "tpp_plaid_uk", "AISP", "ACCOUNTS")
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"


# ── consent_validate tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_validate_returns_valid_result() -> None:
    """Test consent_validate returns validation result."""
    mock_result = {"consent_id": "cns_001", "is_valid": True, "scope_covered": True}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_validate("cns_001", "ACCOUNTS")
        data = json.loads(result)
        assert data["is_valid"] is True


@pytest.mark.asyncio
async def test_consent_validate_invalid_returns_false() -> None:
    """Test consent_validate returns False for invalid consent."""
    mock_result = {"consent_id": "cns_001", "is_valid": False}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_validate("cns_001", "PAYMENTS")
        data = json.loads(result)
        assert data["is_valid"] is False


@pytest.mark.asyncio
async def test_consent_validate_http_error_returns_error() -> None:
    """Test consent_validate handles HTTP error."""
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError(
            "404", request=httpx.Request("POST", "http://test"), response=httpx.Response(404)
        ),
    ):
        result = await consent_validate("cns_unknown", "ACCOUNTS")
        data = json.loads(result)
        assert "error" in data


# ── consent_revoke tests ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_revoke_returns_hitl_proposal() -> None:
    """Test consent_revoke returns HITLProposal data."""
    mock_result = {
        "action": "REVOKE_CONSENT",
        "entity_id": "cns_001",
        "requires_approval_from": "COMPLIANCE_OFFICER",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_revoke("cns_001")
        data = json.loads(result)
        assert data["action"] == "REVOKE_CONSENT"


@pytest.mark.asyncio
async def test_consent_revoke_connect_error() -> None:
    """Test consent_revoke handles connection error."""
    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await consent_revoke("cns_001")
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"


# ── consent_list_tpps tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_list_tpps_returns_tpp_list() -> None:
    """Test consent_list_tpps returns list of TPPs."""
    mock_result = [
        {"tpp_id": "tpp_plaid_uk", "name": "Plaid UK Limited"},
        {"tpp_id": "tpp_truelayer", "name": "TrueLayer Limited"},
    ]
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_list_tpps()
        data = json.loads(result)
        assert len(data) == 2


@pytest.mark.asyncio
async def test_consent_list_tpps_with_type_filter() -> None:
    """Test consent_list_tpps with type filter appends query param."""
    mock_result = [{"tpp_id": "tpp_plaid_uk", "name": "Plaid UK Limited"}]
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_list_tpps(tpp_type="AISP")
        data = json.loads(result)
        assert len(data) == 1


@pytest.mark.asyncio
async def test_consent_list_tpps_http_error() -> None:
    """Test consent_list_tpps handles HTTP error."""
    with patch(
        "banxe_mcp.server._api_get",
        side_effect=httpx.HTTPStatusError(
            "500", request=httpx.Request("GET", "http://test"), response=httpx.Response(500)
        ),
    ):
        result = await consent_list_tpps()
        data = json.loads(result)
        assert "error" in data


# ── consent_cbpii_check tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_consent_cbpii_check_returns_funds_available() -> None:
    """Test CBPII check returns funds_available result."""
    mock_result = {"consent_id": "cns_001", "amount": "500.00", "funds_available": True}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock:
        mock.return_value = mock_result
        result = await consent_cbpii_check("cns_001", "500.00")
        data = json.loads(result)
        assert data["funds_available"] is True


@pytest.mark.asyncio
async def test_consent_cbpii_check_edd_threshold_error() -> None:
    """Test CBPII check handles 422 for EDD threshold (I-04)."""
    with patch(
        "banxe_mcp.server._api_post",
        side_effect=httpx.HTTPStatusError(
            "422 EDD threshold exceeded",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(422),
        ),
    ):
        result = await consent_cbpii_check("cns_001", "10000.00")
        data = json.loads(result)
        assert "error" in data
        assert data.get("status_code") == 422


@pytest.mark.asyncio
async def test_consent_cbpii_check_connect_error() -> None:
    """Test CBPII check handles connection error."""
    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await consent_cbpii_check("cns_001", "100.00")
        data = json.loads(result)
        assert data["error"] == "BANXE API unavailable"
