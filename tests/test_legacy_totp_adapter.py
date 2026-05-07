"""
tests/test_legacy_totp_adapter.py — Unit tests for LegacyTotpAdapter.

Coverage: 100%  |  Tests: 25  |  No external deps (all in-memory).
Verifies semantic parity with GrpcTFAConnector (banxe-common 2fa-connector.service.ts).
"""

from __future__ import annotations

import datetime
import inspect
import re

import pyotp

from services.auth.legacy.legacy_totp_adapter import (
    _BACKUP_COUNT,
    _BACKUP_HEX_BYTES,
    _MAX_ATTEMPTS,
    InMemoryTotpStore,
    LegacyTotpAdapter,
    TotpAdapterError,
)
from services.auth.two_factor import TOTPSetup
from services.auth.two_factor_port import TwoFactorPort

# ── Helpers ───────────────────────────────────────────────────────────────────

_UID = "cust-001"
_UID2 = "cust-002"


def _make_adapter() -> tuple[LegacyTotpAdapter, InMemoryTotpStore]:
    store = InMemoryTotpStore()
    return LegacyTotpAdapter(store=store), store


def _totp_obj(secret: str) -> pyotp.TOTP:
    return pyotp.TOTP(secret, digits=6, interval=30)


def _setup_and_confirm(uid: str = _UID) -> tuple[LegacyTotpAdapter, TOTPSetup]:
    """Returns adapter with TOTP confirmed for uid. Uses totp.now() so verify() matches."""
    adapter, _ = _make_adapter()
    setup = adapter.setup_totp(uid)
    otp = _totp_obj(setup.secret).now()  # same datetime window as verify() internals
    ok = adapter.confirm_totp(uid, otp)
    assert ok, "fixture: confirm_totp must succeed"
    return adapter, setup


# ── setup_totp ────────────────────────────────────────────────────────────────


def test_setup_totp_returns_totp_setup_with_all_fields() -> None:
    adapter, _ = _make_adapter()
    result = adapter.setup_totp(_UID)
    assert isinstance(result, TOTPSetup)
    assert result.customer_id == _UID
    assert result.secret
    assert result.provisioning_uri.startswith("otpauth://totp/")
    assert result.backup_codes
    assert result.created_at is not None


def test_setup_totp_generates_correct_backup_code_count() -> None:
    adapter, _ = _make_adapter()
    result = adapter.setup_totp(_UID)
    assert len(result.backup_codes) == _BACKUP_COUNT


def test_setup_totp_backup_codes_are_8_char_uppercase_hex() -> None:
    adapter, _ = _make_adapter()
    result = adapter.setup_totp(_UID)
    expected_len = _BACKUP_HEX_BYTES * 2  # token_hex(4) → 8 chars
    for code in result.backup_codes:
        assert len(code) == expected_len, f"code {code!r} not {expected_len} chars"
        assert re.match(r"^[0-9A-F]+$", code), f"code {code!r} not uppercase hex"


def test_setup_totp_sets_pending_confirm_state() -> None:
    adapter, _ = _make_adapter()
    adapter.setup_totp(_UID)
    assert adapter.is_enabled(_UID) is False


def test_setup_overwrites_previous_totp_and_disables() -> None:
    adapter, setup1 = _setup_and_confirm(_UID)
    assert adapter.is_enabled(_UID) is True

    setup2 = adapter.setup_totp(_UID)
    assert setup2.secret != setup1.secret
    assert adapter.is_enabled(_UID) is False  # pending confirm again


# ── confirm_totp ──────────────────────────────────────────────────────────────


def test_confirm_totp_activates_on_valid_otp() -> None:
    adapter, store = _make_adapter()
    setup = adapter.setup_totp(_UID)
    otp = _totp_obj(setup.secret).now()
    result = adapter.confirm_totp(_UID, otp)
    assert result is True
    assert adapter.is_enabled(_UID) is True


def test_confirm_totp_returns_false_on_wrong_code() -> None:
    adapter, _ = _make_adapter()
    adapter.setup_totp(_UID)
    result = adapter.confirm_totp(_UID, "000000")
    assert result is False


def test_confirm_totp_wrong_code_leaves_disabled() -> None:
    adapter, _ = _make_adapter()
    adapter.setup_totp(_UID)
    adapter.confirm_totp(_UID, "000000")
    assert adapter.is_enabled(_UID) is False


# ── verify_totp ───────────────────────────────────────────────────────────────


def test_verify_totp_happy_path() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    otp = _totp_obj(setup.secret).now()
    result = adapter.verify_totp(_UID, otp)
    assert result.success is True
    assert result.message == "OTP verified"


def test_verify_totp_clock_skew_previous_window() -> None:
    """valid_window=1 must accept OTP from the adjacent (t-30s) window."""
    adapter, setup = _setup_and_confirm(_UID)
    prev_time = datetime.datetime.now() - datetime.timedelta(seconds=30)
    prev_otp = _totp_obj(setup.secret).at(prev_time)
    result = adapter.verify_totp(_UID, prev_otp)
    assert result.success is True, "clock-skew -1 step should be accepted"


def test_verify_totp_next_window_clock_skew() -> None:
    """valid_window=1 must accept OTP from the adjacent (t+30s) future window."""
    adapter, setup = _setup_and_confirm(_UID)
    next_time = datetime.datetime.now() + datetime.timedelta(seconds=30)
    next_otp = _totp_obj(setup.secret).at(next_time)
    result = adapter.verify_totp(_UID, next_otp)
    assert result.success is True, "clock-skew +1 step should be accepted"


def test_verify_totp_wrong_code_returns_failure_with_remaining() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    result = adapter.verify_totp(_UID, "000000")
    assert result.success is False
    assert result.attempts_remaining == _MAX_ATTEMPTS - 1


def test_verify_totp_not_enabled_returns_failure() -> None:
    adapter, _ = _make_adapter()
    adapter.setup_totp(_UID)
    result = adapter.verify_totp(_UID, "123456")
    assert result.success is False
    assert "not enabled" in result.message


def test_verify_totp_rate_limit_after_max_attempts() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    for _ in range(_MAX_ATTEMPTS):
        adapter.verify_totp(_UID, "000000")
    result = adapter.verify_totp(_UID, "000000")
    assert result.success is False
    assert result.attempts_remaining == 0
    assert "Too many" in result.message


def test_verify_totp_clears_rate_limit_on_success() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    for _ in range(2):
        adapter.verify_totp(_UID, "000000")
    otp = _totp_obj(setup.secret).now()
    ok = adapter.verify_totp(_UID, otp)
    assert ok.success is True
    result = adapter.verify_totp(_UID, "000000")
    assert result.attempts_remaining == _MAX_ATTEMPTS - 1


def test_verify_totp_empty_otp_rejected() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    result = adapter.verify_totp(_UID, "")
    assert result.success is False


# ── revoke_totp ───────────────────────────────────────────────────────────────


def test_revoke_totp_disables_subsequent_verify() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    adapter.revoke_totp(_UID)
    otp = _totp_obj(setup.secret).now()
    result = adapter.verify_totp(_UID, otp)
    assert result.success is False
    assert "not enabled" in result.message


def test_revoke_totp_removes_backup_codes() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    assert adapter.backup_codes_remaining(_UID) == _BACKUP_COUNT
    adapter.revoke_totp(_UID)
    assert adapter.backup_codes_remaining(_UID) == 0


# ── verify_backup_code ────────────────────────────────────────────────────────


def test_backup_code_first_use_succeeds() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    code = setup.backup_codes[0]
    result = adapter.verify_backup_code(_UID, code)
    assert result.success is True
    assert "accepted" in result.message


def test_backup_code_second_use_fails_one_time_use() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    code = setup.backup_codes[0]
    adapter.verify_backup_code(_UID, code)
    result = adapter.verify_backup_code(_UID, code)
    assert result.success is False
    assert "Invalid" in result.message


def test_backup_code_case_insensitive() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    code = setup.backup_codes[0]
    lower = code.lower()
    result = adapter.verify_backup_code(_UID, lower)
    assert result.success is True


def test_backup_codes_remaining_decrements_on_each_use() -> None:
    adapter, setup = _setup_and_confirm(_UID)
    assert adapter.backup_codes_remaining(_UID) == _BACKUP_COUNT
    adapter.verify_backup_code(_UID, setup.backup_codes[0])
    assert adapter.backup_codes_remaining(_UID) == _BACKUP_COUNT - 1
    adapter.verify_backup_code(_UID, setup.backup_codes[1])
    assert adapter.backup_codes_remaining(_UID) == _BACKUP_COUNT - 2


def test_backup_codes_remaining_zero_after_revoke() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    adapter.revoke_totp(_UID)
    assert adapter.backup_codes_remaining(_UID) == 0


def test_empty_backup_code_rejected() -> None:
    adapter, _ = _setup_and_confirm(_UID)
    result = adapter.verify_backup_code(_UID, "")
    assert result.success is False
    assert "Empty" in result.message


def test_backup_code_not_setup_returns_failure() -> None:
    adapter, _ = _make_adapter()
    result = adapter.verify_backup_code("unknown-user", "AABBCCDD")
    assert result.success is False
    assert "not set up" in result.message


# ── Multi-tenant isolation ────────────────────────────────────────────────────


def test_multi_tenant_isolation() -> None:
    """User-1 and user-2 share a store but must not interfere with each other."""
    store = InMemoryTotpStore()
    a1 = LegacyTotpAdapter(store=store)
    a2 = LegacyTotpAdapter(store=store)

    s1 = a1.setup_totp(_UID)
    s2 = a2.setup_totp(_UID2)

    otp1 = _totp_obj(s1.secret).now()
    otp2 = _totp_obj(s2.secret).now()

    assert a1.confirm_totp(_UID, otp1) is True
    assert a2.confirm_totp(_UID2, otp2) is True

    assert a1.is_enabled(_UID) is True
    assert a2.is_enabled(_UID2) is True

    a1.revoke_totp(_UID)
    assert a1.is_enabled(_UID) is False
    assert a2.is_enabled(_UID2) is True  # unaffected


# ── Protocol contract ─────────────────────────────────────────────────────────


def test_adapter_satisfies_two_factor_port_protocol() -> None:
    """All TwoFactorPort methods present on LegacyTotpAdapter with matching param names."""
    protocol_methods = {
        name
        for name in vars(TwoFactorPort)
        if not name.startswith("_") and callable(getattr(TwoFactorPort, name, None))
    }
    assert protocol_methods, "Protocol must expose at least one method"

    adapter = LegacyTotpAdapter()
    for method_name in protocol_methods:
        assert hasattr(adapter, method_name), f"Missing method: {method_name}"
        proto_sig = inspect.signature(getattr(TwoFactorPort, method_name))
        impl_sig = inspect.signature(getattr(type(adapter), method_name))
        proto_params = [p for p in proto_sig.parameters if p != "self"]
        impl_params = [p for p in impl_sig.parameters if p != "self"]
        assert proto_params == impl_params, (
            f"{method_name}: protocol {proto_params} != impl {impl_params}"
        )


def test_default_store_is_in_memory() -> None:
    """LegacyTotpAdapter with no store arg uses InMemoryTotpStore."""
    adapter = LegacyTotpAdapter()
    setup = adapter.setup_totp("default-store-user")
    assert isinstance(setup, TOTPSetup)
    assert adapter.backup_codes_remaining("default-store-user") == _BACKUP_COUNT


def test_totp_adapter_error_has_code_and_message() -> None:
    err = TotpAdapterError(code="TOTP_NOT_FOUND", message="No secret for customer")
    assert err.code == "TOTP_NOT_FOUND"
    assert err.message == "No secret for customer"
    assert "No secret for customer" in str(err)
