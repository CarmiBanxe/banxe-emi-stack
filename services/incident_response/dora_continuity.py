"""
dora_continuity.py — DORA DR/BCP continuity + ICT major-incident classification
SP-THIN GAP-059 | DORA (Reg. (EU) 2022/2554) ICT resilience | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
The Digital Operational Resilience Act (DORA) requires a Disaster-Recovery /
Business-Continuity layer: a registry of critical functions with RTO/RPO targets,
continuity-scenario evaluation (does the recovery meet RTO/RPO?), and ICT
major-incident classification with reporting deadlines. This complements
`incident_signal_port.py` (signal ingestion) — it does NOT reimplement it.

Regulatory basis:
  - DORA Reg. (EU) 2022/2554 — ICT operational resilience, major-incident reporting
  - Durations are Decimal/int (no float) to keep thresholds exact
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class IncidentClass(str, Enum):
    MAJOR = "MAJOR"  # DORA major ICT-related incident — reportable
    SIGNIFICANT = "SIGNIFICANT"
    MINOR = "MINOR"


@dataclass(frozen=True)
class CriticalFunction:
    name: str
    rto_hours: Decimal  # recovery time objective
    rpo_minutes: Decimal  # recovery point objective


@dataclass(frozen=True)
class ContinuityScenario:
    function: CriticalFunction
    actual_recovery_hours: Decimal
    actual_data_loss_minutes: Decimal


@dataclass(frozen=True)
class ContinuityResult:
    function_name: str
    rto_met: bool
    rpo_met: bool
    within_tolerance: bool


@dataclass(frozen=True)
class DoraIncidentAssessment:
    incident_class: IncidentClass
    clients_affected: int
    downtime_hours: Decimal
    reportable: bool
    initial_report_deadline_hours: int  # DORA: 4h from classification for major
    dora_ref: str = "Reg. (EU) 2022/2554"


# DORA major / significant thresholds (sandbox-illustrative; calibrated in prod).
_MAJOR_CLIENTS = 1000
_MAJOR_DOWNTIME_H = Decimal("2")
_SIGNIFICANT_CLIENTS = 100
_SIGNIFICANT_DOWNTIME_H = Decimal("1")
_MAJOR_REPORT_DEADLINE_H = 4


class DoraContinuityService:
    """DR/BCP continuity evaluation + DORA major-incident classification."""

    def evaluate_continuity(self, scenario: ContinuityScenario) -> ContinuityResult:
        rto_met = scenario.actual_recovery_hours <= scenario.function.rto_hours
        rpo_met = scenario.actual_data_loss_minutes <= scenario.function.rpo_minutes
        return ContinuityResult(
            function_name=scenario.function.name,
            rto_met=rto_met,
            rpo_met=rpo_met,
            within_tolerance=rto_met and rpo_met,
        )

    def classify_incident(
        self, *, clients_affected: int, downtime_hours: Decimal
    ) -> DoraIncidentAssessment:
        if clients_affected >= _MAJOR_CLIENTS or downtime_hours >= _MAJOR_DOWNTIME_H:
            incident_class = IncidentClass.MAJOR
        elif clients_affected >= _SIGNIFICANT_CLIENTS or downtime_hours >= _SIGNIFICANT_DOWNTIME_H:
            incident_class = IncidentClass.SIGNIFICANT
        else:
            incident_class = IncidentClass.MINOR
        reportable = incident_class is IncidentClass.MAJOR
        return DoraIncidentAssessment(
            incident_class=incident_class,
            clients_affected=clients_affected,
            downtime_hours=downtime_hours,
            reportable=reportable,
            initial_report_deadline_hours=_MAJOR_REPORT_DEADLINE_H if reportable else 0,
        )
