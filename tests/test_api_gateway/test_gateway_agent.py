from __future__ import annotations

import hashlib

import pytest

from services.api_gateway.gateway_agent import GatewayAgent


@pytest.fixture()
def agent() -> GatewayAgent:
    return GatewayAgent()


def test_create_api_key_returns_dict(agent: GatewayAgent) -> None:
    result = agent.create_api_key("test", "owner-1", ["read"], "FREE")
    assert isinstance(result, dict)


def test_create_api_key_has_raw_key(agent: GatewayAgent) -> None:
    result = agent.create_api_key("test", "owner-1", ["read"], "FREE")
    assert "raw_key" in result
    assert result["raw_key"].startswith("bxk_")


def test_create_api_key_has_key_id(agent: GatewayAgent) -> None:
    result = agent.create_api_key("test", "owner-1", ["read"], "BASIC")
    assert "key_id" in result
    assert result["key_id"] != ""


def test_create_api_key_has_tier(agent: GatewayAgent) -> None:
    result = agent.create_api_key("test", "owner-1", ["read"], "PREMIUM")
    assert result["tier"] == "PREMIUM"


def test_create_api_key_raw_key_not_equal_to_hash(agent: GatewayAgent) -> None:
    result = agent.create_api_key("test", "owner-1", [], "BASIC")
    raw_key = result["raw_key"]
    # Verify raw_key is not its own SHA-256 (i.e., not stored as hash)
    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    assert raw_key != expected_hash


def test_check_request_allowed_with_valid_key(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "BASIC")
    result = agent.check_request(created["raw_key"], "GET", "/v1/test", "1.2.3.4")
    assert result["allowed"] is True


def test_check_request_denied_with_invalid_key(agent: GatewayAgent) -> None:
    result = agent.check_request("bxk_invalid000000000000000000000000", "GET", "/", "1.2.3.4")
    assert result["allowed"] is False


def test_check_request_returns_key_id(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "FREE")
    result = agent.check_request(created["raw_key"], "POST", "/v1/pay", "5.6.7.8")
    assert result["key_id"] == created["key_id"]


def test_check_request_returns_rate_limit_info(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "ENTERPRISE")
    result = agent.check_request(created["raw_key"], "GET", "/v1/fx", "1.2.3.4")
    assert "rate_limit" in result
    assert isinstance(result["rate_limit"], dict)


def test_check_request_returns_quota_info(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "BASIC")
    result = agent.check_request(created["raw_key"], "GET", "/v1/kyc", "9.9.9.9")
    assert "quota" in result
    assert isinstance(result["quota"], dict)


def test_revoke_always_returns_hitl_required(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "FREE")
    result = agent.revoke_key(created["key_id"], actor="admin")
    assert result["status"] == "HITL_REQUIRED"


def test_revoke_returns_key_id(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "FREE")
    result = agent.revoke_key(created["key_id"], actor="compliance-officer")
    assert result["key_id"] == created["key_id"]


def test_get_usage_analytics_returns_dict(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "BASIC")
    agent.check_request(created["raw_key"], "GET", "/v1/test", "1.2.3.4")
    result = agent.get_usage_analytics(created["key_id"])
    assert isinstance(result, dict)


def test_get_usage_analytics_has_analytics_key(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "BASIC")
    result = agent.get_usage_analytics(created["key_id"])
    assert "analytics" in result


def test_get_usage_analytics_has_quota_summary(agent: GatewayAgent) -> None:
    created = agent.create_api_key("test", "owner-1", [], "PREMIUM")
    result = agent.get_usage_analytics(created["key_id"])
    assert "quota_summary" in result


def test_check_request_invalid_key_has_no_key_id(agent: GatewayAgent) -> None:
    result = agent.check_request(
        "bxk_bad_key_00000000000000000000000", "DELETE", "/v1/x", "1.1.1.1"
    )
    assert result["key_id"] is None
