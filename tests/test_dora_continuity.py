"""
test_dora_continuity.py — Tests for DORA DR/BCP continuity (SP-THIN GAP-059)
DORA Reg. (EU) 2022/2554 | banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

from services.incident_response.dora_continuity import (
    ContinuityScenario,
    CriticalFunction,
    DoraContinuityService,
    IncidentClass,
)

_PAYMENTS = CriticalFunction(name="payments", rto_hours=Decimal("4"), rpo_minutes=Decimal("15"))


class TestContinuity:
    def test_within_tolerance(self) -> None:
        res = DoraContinuityService().evaluate_continuity(
            ContinuityScenario(_PAYMENTS, Decimal("2"), Decimal("5"))
        )
        assert res.rto_met and res.rpo_met
        assert res.within_tolerance is True

    def test_rto_breached(self) -> None:
        res = DoraContinuityService().evaluate_continuity(
            ContinuityScenario(_PAYMENTS, Decimal("6"), Decimal("5"))
        )
        assert res.rto_met is False
        assert res.within_tolerance is False

    def test_rpo_breached(self) -> None:
        res = DoraContinuityService().evaluate_continuity(
            ContinuityScenario(_PAYMENTS, Decimal("2"), Decimal("60"))
        )
        assert res.rpo_met is False


class TestClassification:
    def test_major_by_clients(self) -> None:
        a = DoraContinuityService().classify_incident(
            clients_affected=5000, downtime_hours=Decimal("0.5")
        )
        assert a.incident_class is IncidentClass.MAJOR
        assert a.reportable is True
        assert a.initial_report_deadline_hours == 4

    def test_major_by_downtime(self) -> None:
        a = DoraContinuityService().classify_incident(
            clients_affected=10, downtime_hours=Decimal("3")
        )
        assert a.incident_class is IncidentClass.MAJOR

    def test_significant(self) -> None:
        a = DoraContinuityService().classify_incident(
            clients_affected=200, downtime_hours=Decimal("0.5")
        )
        assert a.incident_class is IncidentClass.SIGNIFICANT
        assert a.reportable is False

    def test_minor(self) -> None:
        a = DoraContinuityService().classify_incident(
            clients_affected=5, downtime_hours=Decimal("0.1")
        )
        assert a.incident_class is IncidentClass.MINOR
        assert a.initial_report_deadline_hours == 0
