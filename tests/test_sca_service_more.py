"""Additional ScaApplicationService tests — close residual missing lines.

Targets services/auth/sca_application_service.py missing branches:
  - line 76: ValueError → ScaApplicationError(code='invalid_method')
  - lines 127-129: get_sca_application_service() lazy singleton path

Also covers application-boundary delegation invariants:
  - ScaApplicationError.code propagation for verify/resend
  - list_methods passthrough

Canon: ADR-015 ports/adapters; sca_application_service must remain a thin
translation layer — these tests verify error mapping and DI without touching
the service code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import services.auth.sca_application_service as sca_app_module
from services.auth.sca_application_service import (
    ScaApplicationError,
    ScaApplicationService,
    get_sca_application_service,
)
from services.auth.sca_models import SCAChallenge
from services.auth.sca_service import SCAService

# ── line 76: ValueError → invalid_method ─────────────────────────────────────


def test_initiate_challenge_rejects_unsupported_method_with_invalid_method_code():
    app = ScaApplicationService(sca_service=SCAService())

    with pytest.raises(ScaApplicationError) as exc_info:
        app.initiate_challenge(
            customer_id="cust-001",
            transaction_id="txn-001",
            method="sms",  # not in ('otp', 'biometric') → ValueError in domain
        )

    assert exc_info.value.code == "invalid_method"
    assert "sms" in exc_info.value.message


def test_initiate_challenge_too_many_active_maps_to_too_many_active_code(monkeypatch):
    """RuntimeError from domain → ScaApplicationError(code='too_many_active')."""
    from services.auth import sca_service as sca_mod

    monkeypatch.setattr(sca_mod, "SCA_MAX_CONCURRENT", 1)

    app = ScaApplicationService(sca_service=SCAService())
    app.initiate_challenge(
        customer_id="cust-flood",
        transaction_id="txn-flood-1",
        method="otp",
    )

    with pytest.raises(ScaApplicationError) as exc_info:
        app.initiate_challenge(
            customer_id="cust-flood",
            transaction_id="txn-flood-2",
            method="otp",
        )

    assert exc_info.value.code == "too_many_active"


# ── lines 127-129: lazy singleton in get_sca_application_service ─────────────


def test_get_sca_application_service_creates_singleton_on_first_call(monkeypatch):
    monkeypatch.setattr(sca_app_module, "_sca_app_service", None)

    svc = get_sca_application_service()

    assert isinstance(svc, ScaApplicationService)
    assert sca_app_module._sca_app_service is svc


def test_get_sca_application_service_reuses_singleton(monkeypatch):
    monkeypatch.setattr(sca_app_module, "_sca_app_service", None)

    first = get_sca_application_service()
    second = get_sca_application_service()

    assert first is second


# ── verify_challenge error-code mapping (boundary completeness) ──────────────


def _expired_challenge(
    customer_id: str = "cust-x", challenge_id: str = "ch-expired"
) -> SCAChallenge:
    past = datetime.now(tz=UTC) - timedelta(seconds=300)
    return SCAChallenge(
        challenge_id=challenge_id,
        customer_id=customer_id,
        transaction_id="txn-expired",
        method="otp",
        status="pending",
        created_at=past,
        expires_at=past + timedelta(seconds=1),
    )


def test_verify_challenge_not_found_maps_to_challenge_not_found_code():
    app = ScaApplicationService(sca_service=SCAService())

    with pytest.raises(ScaApplicationError) as exc_info:
        app.verify_challenge(challenge_id="missing-id", otp_code="000000")

    assert exc_info.value.code == "challenge_not_found"


def test_verify_challenge_too_many_attempts_maps_to_too_many_attempts_code(monkeypatch):
    """When domain reports attempts_remaining=0, app boundary raises 429-mapped error."""
    from services.auth import sca_service as sca_mod

    monkeypatch.setattr(sca_mod, "SCA_MAX_ATTEMPTS", 1)

    sca = SCAService()
    challenge = sca.create_challenge(
        customer_id="cust-lockout",
        transaction_id="txn-lockout",
        method="otp",
    )
    # First wrong attempt — domain returns attempts_remaining=0 inline.
    app = ScaApplicationService(sca_service=sca)

    with pytest.raises(ScaApplicationError) as exc_info:
        app.verify_challenge(challenge_id=challenge.challenge_id, otp_code="999999")

    assert exc_info.value.code == "too_many_attempts"


# ── resend_challenge error-code mapping ──────────────────────────────────────


def test_resend_challenge_unknown_id_maps_to_challenge_not_found_code():
    app = ScaApplicationService(sca_service=SCAService())

    with pytest.raises(ScaApplicationError) as exc_info:
        app.resend_challenge(challenge_id="ghost-challenge")

    assert exc_info.value.code == "challenge_not_found"


def test_resend_challenge_used_status_maps_to_resend_rejected_code():
    sca = SCAService()
    challenge = sca.create_challenge(
        customer_id="cust-test",
        transaction_id="txn-resend-used",
        method="otp",
    )
    challenge.status = "used"
    sca._store.save(challenge)

    app = ScaApplicationService(sca_service=sca)

    with pytest.raises(ScaApplicationError) as exc_info:
        app.resend_challenge(challenge_id=challenge.challenge_id)

    assert exc_info.value.code == "resend_rejected"


# ── list_methods passthrough ────────────────────────────────────────────────


def test_list_methods_returns_methods_response_for_customer():
    app = ScaApplicationService(sca_service=SCAService())

    response = app.list_methods(customer_id="cust-bio")  # ends with -bio → biometric

    assert response.customer_id == "cust-bio"
    assert "otp" in response.methods
    assert "biometric" in response.methods
    assert response.preferred == "biometric"
