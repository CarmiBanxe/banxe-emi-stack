"""Smoke tests for ADR-028 Step 3: KYC re-trigger operational readiness.

Gap refs: G-KYC-01 (role/UBO change) | G-KYC-02 (jurisdiction change)
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from services.events.event_bus import (
    BanxeEventType,
    KycReTriggerEvent,
    build_kyc_retrigger_event,
)


def test_event_types_registered() -> None:
    """All 3 KYC re-trigger event types exist in BanxeEventType enum."""
    assert hasattr(BanxeEventType, "ROLE_CHANGED")
    assert hasattr(BanxeEventType, "BENEFICIAL_OWNER_CHANGED")
    assert hasattr(BanxeEventType, "JURISDICTION_CHANGED")

    assert BanxeEventType.ROLE_CHANGED in BanxeEventType
    assert BanxeEventType.BENEFICIAL_OWNER_CHANGED in BanxeEventType
    assert BanxeEventType.JURISDICTION_CHANGED in BanxeEventType


def test_build_retrigger_event_all_types() -> None:
    """build_kyc_retrigger_event() returns correct KycReTriggerEvent for each type."""
    expected = {
        BanxeEventType.ROLE_CHANGED: ("HIGH", "G-KYC-01"),
        BanxeEventType.BENEFICIAL_OWNER_CHANGED: ("HIGH", "G-KYC-01"),
        BanxeEventType.JURISDICTION_CHANGED: ("CRITICAL", "G-KYC-02"),
    }

    for event_type, (exp_crit, exp_gap) in expected.items():
        event = build_kyc_retrigger_event(
            event_type=event_type,
            customer_id="smoke-cust-001",
            triggered_by="smoke-test",
            previous_value="old_val",
            new_value="new_val",
        )
        assert isinstance(event, KycReTriggerEvent)
        assert event.event_type == event_type
        assert event.criticality == exp_crit, f"{event_type.name}: expected {exp_crit}"
        assert event.gap_ref == exp_gap, f"{event_type.name}: expected {exp_gap}"
        assert event.customer_id == "smoke-cust-001"


def test_fsm_handles_kyc_retrigger_event() -> None:
    """FSM lifecycle engine accepts KycReTriggerEvent without exception."""
    from services.customer_lifecycle.fsm import KYCLifecycleEngine

    engine = KYCLifecycleEngine()

    for event_type in (
        BanxeEventType.ROLE_CHANGED,
        BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        BanxeEventType.JURISDICTION_CHANGED,
    ):
        result = engine.notify_attribute_change(
            customer_id="smoke-cust-002",
            event_type=event_type,
            triggered_by="smoke-test",
            previous_value="before",
            new_value="after",
        )
        assert isinstance(result, KycReTriggerEvent)
        assert result.event_type == event_type


def test_operational_script_runs() -> None:
    """scripts/kyc-retrigger-check.py exits with code 0."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "kyc-retrigger-check.py"
    assert script.exists(), f"script not found: {script}"

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"script failed:\n{result.stdout}\n{result.stderr}"
    assert "ALL CHECKS PASS" in result.stdout
