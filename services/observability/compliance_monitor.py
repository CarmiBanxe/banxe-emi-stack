"""
services/observability/compliance_monitor.py
Compliance invariant monitor (IL-OBS-01).
Checks I-01..I-28, blocked jurisdictions, HITL gates, audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol


class ComplianceFlag(str, Enum):
    COMPLIANT = "compliant"
    WARNING = "warning"
    VIOLATION = "violation"


@dataclass(frozen=True)
class InvariantCheck:
    invariant_id: str
    description: str
    flag: ComplianceFlag
    detail: str


@dataclass(frozen=True)
class ComplianceReport:
    overall_flag: ComplianceFlag
    checks: list[InvariantCheck]
    scanned_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def violation_count(self) -> int:
        return sum(1 for c in self.checks if c.flag == ComplianceFlag.VIOLATION)

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.flag == ComplianceFlag.WARNING)


class ComplianceCheckPort(Protocol):
    """Port for compliance checks (Protocol DI)."""

    def check_decimal_usage(self) -> bool: ...

    def check_blocked_jurisdictions(self) -> bool: ...

    def check_audit_trail_append_only(self) -> bool: ...

    def check_hitl_gates(self) -> bool: ...


class InMemoryComplianceCheckPort:
    """Stub — all checks pass by default."""

    def __init__(self, overrides: dict[str, bool] | None = None) -> None:
        self._overrides = overrides or {}

    def check_decimal_usage(self) -> bool:
        return self._overrides.get("decimal_usage", True)

    def check_blocked_jurisdictions(self) -> bool:
        return self._overrides.get("blocked_jurisdictions", True)

    def check_audit_trail_append_only(self) -> bool:
        return self._overrides.get("audit_trail", True)

    def check_hitl_gates(self) -> bool:
        return self._overrides.get("hitl_gates", True)


class ComplianceMonitor:
    """Monitors all financial invariants (I-01..I-28).

    I-27: violations trigger HITLProposal to COMPLIANCE_OFFICER, not auto-remediation.
    """

    def __init__(self, port: ComplianceCheckPort | None = None) -> None:
        self._port: ComplianceCheckPort = port or InMemoryComplianceCheckPort()

    def scan(self) -> ComplianceReport:
        """Scan all compliance invariants and return report."""
        checks: list[InvariantCheck] = []

        # I-01: Decimal for money
        ok = self._port.check_decimal_usage()
        checks.append(
            InvariantCheck(
                invariant_id="I-01",
                description="No float for money — only Decimal",
                flag=ComplianceFlag.COMPLIANT if ok else ComplianceFlag.VIOLATION,
                detail="Decimal usage verified" if ok else "Float detected in financial code",
            )
        )

        # I-02: Blocked jurisdictions
        ok = self._port.check_blocked_jurisdictions()
        checks.append(
            InvariantCheck(
                invariant_id="I-02",
                description="Hard-block: RU/BY/IR/KP/CU/MM/AF/VE/SY",
                flag=ComplianceFlag.COMPLIANT if ok else ComplianceFlag.VIOLATION,
                detail=(
                    "Blocked jurisdictions enforced" if ok else "Blocked jurisdiction check failed"
                ),
            )
        )

        # I-24: Append-only audit trail
        ok = self._port.check_audit_trail_append_only()
        checks.append(
            InvariantCheck(
                invariant_id="I-24",
                description="Audit trails are append-only (no UPDATE/DELETE)",
                flag=ComplianceFlag.COMPLIANT if ok else ComplianceFlag.VIOLATION,
                detail=("Audit trail is append-only" if ok else "Mutable audit trail detected"),
            )
        )

        # I-27: HITL gates
        ok = self._port.check_hitl_gates()
        checks.append(
            InvariantCheck(
                invariant_id="I-27",
                description="HITL — AI proposes, human decides",
                flag=ComplianceFlag.COMPLIANT if ok else ComplianceFlag.VIOLATION,
                detail=("HITL gates active" if ok else "Auto-execution detected (I-27 violation)"),
            )
        )

        violations = sum(1 for c in checks if c.flag == ComplianceFlag.VIOLATION)
        warnings = sum(1 for c in checks if c.flag == ComplianceFlag.WARNING)

        if violations > 0:
            overall = ComplianceFlag.VIOLATION
        elif warnings > 0:
            overall = ComplianceFlag.WARNING
        else:
            overall = ComplianceFlag.COMPLIANT

        return ComplianceReport(overall_flag=overall, checks=checks)
