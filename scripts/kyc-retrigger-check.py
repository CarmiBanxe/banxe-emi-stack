#!/usr/bin/env python3
"""Operational check: KYC re-trigger events wiring (ADR-028).

Verifies that all 3 KYC re-trigger event types are registered, buildable,
and wired into the FSM lifecycle engine.

Usage:
    python3 scripts/kyc-retrigger-check.py

Cron (daily):
    0 6 * * * cd /opt/banxe && python3 scripts/kyc-retrigger-check.py >> /var/log/banxe/kyc-retrigger-check.log 2>&1

Exit codes:
    0  all checks PASS
    1  any check FAIL
"""

from __future__ import annotations

import os
import sys

_repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)


def check_event_types_registered() -> tuple[bool, str]:
    """Check that all 3 KYC re-trigger event types exist in BanxeEventType."""
    from services.events.event_bus import BanxeEventType

    required = ["ROLE_CHANGED", "BENEFICIAL_OWNER_CHANGED", "JURISDICTION_CHANGED"]
    missing = [name for name in required if not hasattr(BanxeEventType, name)]
    if missing:
        return False, f"missing enum members: {missing}"
    return True, "all 3 event types registered"


def check_dataclass_importable() -> tuple[bool, str]:
    """Check that KycReTriggerEvent dataclass is importable."""
    try:
        from services.events.event_bus import KycReTriggerEvent  # noqa: F401

        return True, "KycReTriggerEvent importable"
    except ImportError as exc:
        return False, f"import failed: {exc}"


def check_build_function() -> tuple[bool, str]:
    """Check build_kyc_retrigger_event() returns valid events for all 3 types."""
    from services.events.event_bus import (
        BanxeEventType,
        KycReTriggerEvent,
        build_kyc_retrigger_event,
    )

    types = [
        BanxeEventType.ROLE_CHANGED,
        BanxeEventType.BENEFICIAL_OWNER_CHANGED,
        BanxeEventType.JURISDICTION_CHANGED,
    ]
    for event_type in types:
        event = build_kyc_retrigger_event(
            event_type=event_type,
            customer_id="check-cust-001",
            triggered_by="operational-check",
            previous_value="old",
            new_value="new",
        )
        if not isinstance(event, KycReTriggerEvent):
            return False, f"{event_type.name}: returned non-KycReTriggerEvent"
        if not event.criticality:
            return False, f"{event_type.name}: empty criticality"
        if not event.gap_ref:
            return False, f"{event_type.name}: empty gap_ref"
    return True, "build_kyc_retrigger_event valid for all 3 types"


def check_fsm_wiring() -> tuple[bool, str]:
    """Check FSM lifecycle engine handles KYC re-trigger events."""
    from services.customer_lifecycle.fsm import KYCLifecycleEngine
    from services.events.event_bus import BanxeEventType

    engine = KYCLifecycleEngine()
    try:
        result = engine.notify_attribute_change(
            customer_id="check-cust-002",
            event_type=BanxeEventType.ROLE_CHANGED,
            triggered_by="operational-check",
            previous_value="director",
            new_value="shareholder",
        )
    except Exception as exc:
        return False, f"FSM notify_attribute_change raised: {exc}"
    if result is None:
        return False, "FSM returned None instead of KycReTriggerEvent"
    return True, "FSM wiring operational"


def main() -> int:
    checks = [
        ("event_types_registered", check_event_types_registered),
        ("dataclass_importable", check_dataclass_importable),
        ("build_function_valid", check_build_function),
        ("fsm_wiring", check_fsm_wiring),
    ]

    results: list[tuple[str, bool, str]] = []
    for name, fn in checks:
        passed, detail = fn()
        results.append((name, passed, detail))

    all_pass = all(passed for _, passed, _ in results)

    for name, passed, detail in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {detail}")

    print(
        f"\n{'ALL CHECKS PASS' if all_pass else 'SOME CHECKS FAILED'} ({sum(1 for _, p, _ in results if p)}/{len(results)})"
    )
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
