from __future__ import annotations

import hashlib
import re

import pytest

from services.api_gateway.api_key_manager import APIKeyManager
from services.api_gateway.models import KeyStatus, UsageTier


@pytest.fixture()
def manager() -> APIKeyManager:
    return APIKeyManager()


def test_create_key_returns_tuple(manager: APIKeyManager) -> None:
    result = manager.create_key("my-key", "owner-1", ["read"], UsageTier.FREE)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_create_key_raw_key_format(manager: APIKeyManager) -> None:
    raw_key, _ = manager.create_key("k", "o", [], UsageTier.FREE)
    assert raw_key.startswith("bxk_")
    assert len(raw_key) == 36  # "bxk_" + 32 hex chars


def test_create_key_hash_not_equal_to_raw(manager: APIKeyManager) -> None:
    raw_key, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    assert api_key.key_hash != raw_key


def test_create_key_hash_is_sha256(manager: APIKeyManager) -> None:
    raw_key, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    assert api_key.key_hash == expected_hash


def test_create_key_hash_is_hex_64_chars(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.FREE)
    assert len(api_key.key_hash) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", api_key.key_hash)


def test_create_key_status_is_active(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "owner", ["read"], UsageTier.FREE)
    assert api_key.status == KeyStatus.ACTIVE


def test_create_key_stores_owner_and_scope(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "owner-x", ["payments", "kyc"], UsageTier.PREMIUM)
    assert api_key.owner_id == "owner-x"
    assert api_key.scope == ["payments", "kyc"]


def test_verify_key_returns_api_key_for_valid_key(manager: APIKeyManager) -> None:
    raw_key, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    found = manager.verify_key(raw_key)
    assert found is not None
    assert found.key_id == api_key.key_id


def test_verify_key_returns_none_for_invalid(manager: APIKeyManager) -> None:
    result = manager.verify_key("bxk_invalid_raw_key_does_not_exist")
    assert result is None


def test_verify_key_returns_none_for_wrong_key(manager: APIKeyManager) -> None:
    manager.create_key("k", "o", [], UsageTier.FREE)
    result = manager.verify_key("bxk_wronghash00000000000000000000")
    assert result is None


def test_rotate_creates_new_key(manager: APIKeyManager) -> None:
    raw_key, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    new_raw, new_key = manager.rotate_key(api_key.key_id)
    assert new_key.key_id != api_key.key_id
    assert new_raw.startswith("bxk_")


def test_rotate_marks_old_key_rotated(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    manager.rotate_key(api_key.key_id)
    old = manager.get_key(api_key.key_id)
    assert old is not None
    assert old.status == KeyStatus.ROTATED


def test_rotate_new_key_is_active(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    _, new_key = manager.rotate_key(api_key.key_id)
    assert new_key.status == KeyStatus.ACTIVE


def test_rotate_new_key_has_different_hash(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    _, new_key = manager.rotate_key(api_key.key_id)
    assert new_key.key_hash != api_key.key_hash


def test_revoke_always_returns_hitl_required(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.FREE)
    result = manager.revoke_key(api_key.key_id, actor="admin")
    assert result["status"] == "HITL_REQUIRED"
    assert result["key_id"] == api_key.key_id


def test_revoke_does_not_change_key_status(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.FREE)
    manager.revoke_key(api_key.key_id, actor="admin")
    key = manager.get_key(api_key.key_id)
    assert key is not None
    assert key.status == KeyStatus.ACTIVE  # still active — HITL not processed


def test_list_keys_by_owner(manager: APIKeyManager) -> None:
    manager.create_key("k1", "owner-A", [], UsageTier.FREE)
    manager.create_key("k2", "owner-A", [], UsageTier.BASIC)
    manager.create_key("k3", "owner-B", [], UsageTier.FREE)
    keys = manager.list_keys("owner-A")
    assert len(keys) == 2


def test_get_key_returns_correct_key(manager: APIKeyManager) -> None:
    _, api_key = manager.create_key("k", "o", [], UsageTier.ENTERPRISE)
    result = manager.get_key(api_key.key_id)
    assert result is not None
    assert result.key_id == api_key.key_id


def test_get_key_returns_none_for_unknown(manager: APIKeyManager) -> None:
    result = manager.get_key("nonexistent-id")
    assert result is None


def test_rotate_nonexistent_key_raises(manager: APIKeyManager) -> None:
    with pytest.raises(ValueError, match="Key not found"):
        manager.rotate_key("nonexistent-id")


def test_verify_rotated_key_returns_none(manager: APIKeyManager) -> None:
    raw_key, api_key = manager.create_key("k", "o", [], UsageTier.BASIC)
    manager.rotate_key(api_key.key_id)
    result = manager.verify_key(raw_key)
    assert result is None  # old key is ROTATED, not ACTIVE
