"""Unit tests for ADR-028 Step 1: KYC re-trigger event types.

Gap refs: G-KYC-01 (role/UBO change) | G-KYC-02 (jurisdiction change)
"""

from __future__ import annotations

from services.events.event_bus import (
    BanxeEventType,
    KycReTriggerEvent,
    build_kyc_retrigger_event,
)

# ---------------------------------------------------------------------------
# T1-T3: Enum membership
# ---------------------------------------------------------------------------


def test_role_changed_enum_exists() -> None:
    assert BanxeEventType.ROLE_CHANGED == "kyc.role_changed"
    assert BanxeEventType.ROLE_CHANGED in BanxeEventType


def test_beneficial_owner_changed_enum_exists() -> None:
    assert BanxeEventType.BENEFICIAL_OWNER_CHANGED == "kyc.beneficial_owner_changed"
    assert BanxeEventType.BENEFICIAL_OWNER_CHANGED in BanxeEventType


def test_jurisdiction_changed_enum_exists() -> None:
    assert BanxeEventType.JURISDICTION_CHANGED == "kyc.jurisdiction_changed"
    assert BanxeEventType.JURISDICTION_CHANGED in BanxeEventType


# ---------------------------------------------------------------------------
# T4: JURISDICTION_CHANGED → criticality=CRITICAL, gap_ref=G-KYC-02
# ---------------------------------------------------------------------------


def test_build_kyc_retrigger_event_jurisdiction_is_critical() -> None:
    event = build_kyc_retrigger_event(
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        customer_id="cust-001",
        triggered_by="ops-agent",
        previous_value="GB",
        new_value="IR",
    )
    assert isinstance(event, KycReTriggerEvent)
    assert event.criticality == "CRITICAL"
    assert event.gap_ref == "G-KYC-02"
    assert event.customer_id == "cust-001"
    assert event.previous_value == "GB"
    assert event.new_value == "IR"


# ---------------------------------------------------------------------------
# T5: ROLE_CHANGED → criticality=HIGH, gap_ref=G-KYC-01
# ---------------------------------------------------------------------------


def test_build_kyc_retrigger_event_role_is_high() -> None:
    event = build_kyc_retrigger_event(
        event_type=BanxeEventType.ROLE_CHANGED,
        customer_id="cust-002",
        triggered_by="admin",
        previous_value="DIRECTOR",
        new_value="UBO",
    )
    assert event.criticality == "HIGH"
    assert event.gap_ref == "G-KYC-01"


# ---------------------------------------------------------------------------
# T6: BENEFICIAL_OWNER_CHANGED → criticality=HIGH, gap_ref=G-KYC-01
# ---------------------------------------------------------------------------


def test_build_kyc_retrigger_event_ubo_is_high() -> None:
    event = build_kyc_retrigger_event(
        event_type=BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        customer_id="cust-003",
        triggered_by="kyc-agent",
        previous_value="Alice Smith",
        new_value="Bob Jones",
    )
    assert event.criticality == "HIGH"
    assert event.gap_ref == "G-KYC-01"


# ---------------------------------------------------------------------------
# T7: KycReTriggerEvent dataclass fields are all present
# ---------------------------------------------------------------------------


def test_kyc_retrigger_event_dataclass_fields() -> None:
    event = KycReTriggerEvent(
        event_type=BanxeEventType.JURISDICTION_CHANGED,
        customer_id="cust-x",
        triggered_by="system",
        previous_value="US",
        new_value="KP",
        criticality="CRITICAL",
        gap_ref="G-KYC-02",
    )
    assert event.event_type is BanxeEventType.JURISDICTION_CHANGED
    assert event.triggered_by == "system"
    assert event.criticality == "CRITICAL"
    assert event.gap_ref == "G-KYC-02"


# ---------------------------------------------------------------------------
# T8: Existing BanxeEventType values are unchanged
# ---------------------------------------------------------------------------


def test_existing_event_types_unchanged() -> None:
    assert BanxeEventType.PAYMENT_COMPLETED == "payment.completed"
    assert BanxeEventType.KYC_APPROVED == "kyc.approved"
    assert BanxeEventType.SAFEGUARDING_SHORTFALL == "safeguarding.shortfall"
    assert BanxeEventType.FIN060_GENERATED == "reporting.fin060_generated"
