from __future__ import annotations

import pytest

from services.api_gateway.ip_filter import IPFilter
from services.api_gateway.models import GeoAction


@pytest.fixture()
def ip_filter() -> IPFilter:
    return IPFilter()


def test_is_allowed_no_allowlist_allows_all(ip_filter: IPFilter) -> None:
    assert ip_filter.is_allowed("192.168.1.1", "key-1") is True


def test_is_allowed_no_allowlist_allows_any_ip(ip_filter: IPFilter) -> None:
    assert ip_filter.is_allowed("10.0.0.1", "key-2") is True


def test_is_allowed_with_allow_entry_permits_listed_ip(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-3", "192.168.1.0/24", GeoAction.ALLOW)
    assert ip_filter.is_allowed("192.168.1.50", "key-3") is True


def test_is_allowed_with_allow_entry_blocks_unlisted_ip(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-4", "192.168.1.0/24", GeoAction.ALLOW)
    assert ip_filter.is_allowed("10.0.0.1", "key-4") is False


def test_is_allowed_block_action_blocks_matching_cidr(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-5", "10.0.0.0/8", GeoAction.BLOCK)
    assert ip_filter.is_allowed("10.1.2.3", "key-5") is False


def test_is_allowed_block_action_allows_non_matching(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-6", "10.0.0.0/8", GeoAction.BLOCK)
    assert ip_filter.is_allowed("192.168.1.1", "key-6") is True


def test_add_to_allowlist_returns_entry(ip_filter: IPFilter) -> None:
    entry = ip_filter.add_to_allowlist("key-7", "172.16.0.0/12", GeoAction.ALLOW)
    assert entry.cidr == "172.16.0.0/12"
    assert entry.action == GeoAction.ALLOW
    assert entry.key_id == "key-7"


def test_add_to_allowlist_entry_has_entry_id(ip_filter: IPFilter) -> None:
    entry = ip_filter.add_to_allowlist("key-8", "10.0.0.0/8", GeoAction.ALLOW)
    assert entry.entry_id != ""


def test_validate_cidr_valid_network(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("192.168.1.0/24") is True


def test_validate_cidr_valid_host(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("10.0.0.1/32") is True


def test_validate_cidr_valid_ipv6(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("2001:db8::/32") is True


def test_validate_cidr_invalid_string(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("not-an-ip") is False


def test_validate_cidr_invalid_mask(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("192.168.1.0/99") is False


def test_validate_cidr_empty_string(ip_filter: IPFilter) -> None:
    assert ip_filter.validate_cidr("") is False


def test_is_allowed_exact_host_cidr(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-9", "203.0.113.42/32", GeoAction.ALLOW)
    assert ip_filter.is_allowed("203.0.113.42", "key-9") is True
    assert ip_filter.is_allowed("203.0.113.43", "key-9") is False


def test_multiple_allow_entries(ip_filter: IPFilter) -> None:
    ip_filter.add_to_allowlist("key-10", "10.0.0.0/8", GeoAction.ALLOW)
    ip_filter.add_to_allowlist("key-10", "172.16.0.0/12", GeoAction.ALLOW)
    assert ip_filter.is_allowed("10.5.5.5", "key-10") is True
    assert ip_filter.is_allowed("172.20.1.1", "key-10") is True
    assert ip_filter.is_allowed("8.8.8.8", "key-10") is False


def test_block_action_geo_blocked_cidr(ip_filter: IPFilter) -> None:
    # Stub blocked CIDR is "0.0.0.0/32" — only that exact IP is blocked
    # Test that normal IPs are allowed (geo block stub doesn't affect them)
    assert ip_filter.is_allowed("1.2.3.4", "key-11") is True
