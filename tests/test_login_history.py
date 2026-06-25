"""MIG genuine-gap #2 — advisory login-history audit (descriptive, no live auth, PII-masked).

characterization: LoginHistoryPort / LoginHistoryRecord / LoginOutcome shape. contract: record shape;
timestamp supplied by caller; IP masked. fence: no midaz/ledger/kyc imports; no wall-clock
(datetime.now/Date.now); PII masked (no raw IP stored); no float usage.
"""

from dataclasses import fields
from pathlib import Path

from services.auth.login_history import (
    LoginHistoryPort,
    LoginHistoryRecord,
    LoginOutcome,
    SandboxLoginHistoryProvider,
    mask_ip,
)


def _p() -> SandboxLoginHistoryProvider:
    return SandboxLoginHistoryProvider()


def test_port_and_record_shape() -> None:
    assert issubclass(SandboxLoginHistoryProvider, LoginHistoryPort)
    assert {f.name for f in fields(LoginHistoryRecord)} == {
        "event_id",
        "login_event",
        "timestamp",
        "masked_ip",
        "user_ref",
        "outcome",
        "source",
    }
    assert {o.value for o in LoginOutcome} == {
        "success",
        "failure",
        "mfa_required",
        "locked",
        "expired",
    }


def test_record_timestamp_param_and_masked_ip() -> None:
    rec = _p().record(
        login_event="password_login",
        timestamp="2026-06-21T22:00:00Z",
        ip="203.0.113.42",
        user_ref="user-opaque-1",
        outcome=LoginOutcome.SUCCESS,
    )
    assert rec.timestamp == "2026-06-21T22:00:00Z"  # caller-supplied
    assert rec.masked_ip == "203.0.113.x"  # PII masked, no raw last octet
    assert "42" not in rec.masked_ip
    assert rec.outcome is LoginOutcome.SUCCESS


def test_mask_ip_variants() -> None:
    assert mask_ip("10.1.2.3") == "10.1.2.x"
    assert mask_ip("2001:db8::1").endswith(":****")
    assert mask_ip("garbage") == "****"  # fail-closed mask


def test_get_event_fail_closed() -> None:
    p = _p()
    r = p.record(
        login_event="x",
        timestamp="2026-06-21T00:00:00Z",
        ip="1.1.1.1",
        user_ref="u",
        outcome=LoginOutcome.FAILURE,
    )
    assert p.get_event(r.event_id) is not None
    assert p.get_event("LH-unknown") is None  # fail-closed


def test_fence_no_midaz_ledger_kyc_no_wallclock_no_float() -> None:
    import services.auth.login_history as mod

    text = Path(mod.__file__).read_text()
    import_lines = "\n".join(
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import: {bad}"
    # no wall-clock CALLS (timestamp must be caller-supplied; docstring may mention the names)
    low = text.lower()
    assert (
        "datetime.now(" not in low
        and "datetime.utcnow(" not in low
        and "date.now(" not in low
        and ".utcnow(" not in low
    )
    # no float usage
    assert "float(" not in text and ": float" not in text and "-> float" not in text


def test_di_injected_id_generator_deterministic() -> None:
    # DI: id_generator injected via constructor (deterministic in tests; CodeRabbit DI fix)
    seq = iter(["LH-aaa", "LH-bbb"])
    p = SandboxLoginHistoryProvider(id_generator=lambda: next(seq))
    r = p.record(
        login_event="x",
        timestamp="2026-06-21T00:00:00Z",
        ip="1.2.3.4",
        user_ref="u",
        outcome=LoginOutcome.SUCCESS,
    )
    assert r.event_id == "LH-aaa"


def test_collision_safe_no_silent_overwrite() -> None:
    # audit integrity: colliding id must not overwrite a prior record (CodeRabbit fix)
    import pytest

    const = SandboxLoginHistoryProvider(id_generator=lambda: "LH-fixed")
    const.record(
        login_event="a",
        timestamp="2026-06-21T00:00:00Z",
        ip="1.1.1.1",
        user_ref="u",
        outcome=LoginOutcome.SUCCESS,
    )
    with pytest.raises(RuntimeError):  # fail-closed after retries, no overwrite
        const.record(
            login_event="b",
            timestamp="2026-06-21T00:01:00Z",
            ip="2.2.2.2",
            user_ref="u",
            outcome=LoginOutcome.FAILURE,
        )
    assert len(const.list_history()) == 1  # prior audit record preserved
