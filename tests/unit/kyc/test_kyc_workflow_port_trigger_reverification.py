"""Unit tests for KYCWorkflowPort.trigger_reverification() surface + Mock
behavior (ADR-028 Step 4).
"""

from __future__ import annotations

from services.kyc.kyc_port import KYC_RETRIGGER_TYPES, KYCWorkflowPort
from services.kyc.mock_kyc_workflow import MockKYCWorkflow


def test_port_protocol_includes_trigger_reverification_method() -> None:
    # Protocol surface check via attribute lookup (Protocols are not
    # runtime-checkable by default; method existence is the contract).
    assert hasattr(KYCWorkflowPort, "trigger_reverification")
    assert callable(KYCWorkflowPort.trigger_reverification)


def test_mock_trigger_reverification_records_invocation() -> None:
    mock = MockKYCWorkflow()
    mock.trigger_reverification(
        customer_id="cust-1",
        trigger_type="role_changed",
        trigger_payload={"old": "X", "new": "Y"},
        requested_by="lifecycle-observer",
    )
    assert len(mock.trigger_reverification_calls) == 1
    call = mock.trigger_reverification_calls[0]
    assert call["customer_id"] == "cust-1"
    assert call["trigger_type"] == "role_changed"
    assert call["trigger_payload"] == {"old": "X", "new": "Y"}
    assert call["requested_by"] == "lifecycle-observer"


def test_kyc_retrigger_types_tuple_has_5_canonical_values() -> None:
    assert isinstance(KYC_RETRIGGER_TYPES, tuple)
    assert set(KYC_RETRIGGER_TYPES) == {
        "role_changed",
        "beneficial_owner_changed",
        "sanctions_match",
        "jurisdiction_changed",
        "periodic_review_due",
    }
    assert len(KYC_RETRIGGER_TYPES) == 5


def test_mock_trigger_reverification_accepts_all_5_canonical_trigger_types() -> None:
    mock = MockKYCWorkflow()
    for tt in KYC_RETRIGGER_TYPES:
        mock.trigger_reverification(
            customer_id=f"cust-for-{tt}",
            trigger_type=tt,
            trigger_payload={"tt": tt},
        )
    assert len(mock.trigger_reverification_calls) == len(KYC_RETRIGGER_TYPES) == 5
    assert {c["trigger_type"] for c in mock.trigger_reverification_calls} == set(
        KYC_RETRIGGER_TYPES
    )


def test_mock_trigger_reverification_does_not_raise_on_unknown_trigger_type() -> None:
    """Port is permissive at the Mock layer — validation happens in the
    audit emitter (which raises ValueError on unknown trigger_type). This
    matches the Mock convention used by the rest of services/kyc/."""
    mock = MockKYCWorkflow()
    mock.trigger_reverification(
        customer_id="cust", trigger_type="anything_goes_at_mock_layer", trigger_payload={}
    )
    assert len(mock.trigger_reverification_calls) == 1
