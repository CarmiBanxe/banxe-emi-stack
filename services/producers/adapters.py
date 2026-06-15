"""
services/producers/adapters.py — WIRED L3 adapters for the compliance producer.

These adapters are the *only* place the producers touch the real L3. Each
implements one of the ports from ``services/producers/ports.py`` by delegating to
an existing L3 service through a minimal structural Protocol (``*_Like``) — so no
concrete L3 class is imported and NO L3 file is edited. They translate an L3
result into an opaque :class:`CheckOutcome` (verdict + ref + non-PII codes).

Mapping rules (ADR-046):
  • AML       — sanctions_block → FAIL; any HITL flag (SAR/EDD/velocity/
                structuring) → ESCALATE; else PASS.
  • Sanctions — CONFIRMED_MATCH → FAIL; POSSIBLE_MATCH → ESCALATE;
                ERROR → ESCALATE; CLEAR → PASS; no resolvable identity → N/A.
  • Fraud     — block → FAIL; hold_for_review / APP-scam / HIGH|CRITICAL risk →
                ESCALATE; else PASS.

R-SEC: outputs carry the L3 report/decision id + policy codes only — never the
matched name, account, or any raw L3 reason string.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from services.agents._lineage import ComplianceResult
from services.aml.tx_monitor import MonitorResult, TxMonitorRequest
from services.fraud.fraud_port import FraudScoringRequest, FraudScoringResult
from services.producers.ports import (
    CheckOutcome,
    ComplianceCheckRequest,
    NullSanctionsIdentity,
    SanctionsIdentityPort,
)
from services.sanctions_screening.models import ScreeningReport, ScreeningResult

# ── Minimal structural views of the L3 services (no concrete import) ──────────


class _TxMonitorLike(Protocol):
    def evaluate(self, req: TxMonitorRequest) -> MonitorResult: ...


class _ScreeningEngineLike(Protocol):
    def screen_entity(
        self,
        entity_name: str,
        entity_type: object,
        nationality: str,
        date_of_birth: str | None = ...,
        requested_by: str = ...,
    ) -> ScreeningReport: ...


class _FraudScorerLike(Protocol):
    def score(self, request: FraudScoringRequest) -> FraudScoringResult: ...


# ── AML adapter (wraps services/aml tx_monitor + thresholds) ─────────────────


class AMLCheckAdapter:
    """Wrap an L3 ``TxMonitorService`` as an :class:`AMLCheckPort`."""

    def __init__(self, tx_monitor: _TxMonitorLike) -> None:
        self._monitor = tx_monitor

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        result = self._monitor.evaluate(
            TxMonitorRequest(
                transaction_id=request.correlation_id,
                customer_id=request.subject_ref,
                entity_type=request.entity_type,
                amount=request.amount,
                currency=request.currency,
                is_pep=request.is_pep,
                is_sanctions_hit=request.is_sanctions_hit,
                is_fx=request.is_fx,
            )
        )
        return CheckOutcome(
            result=_map_aml(result),
            ref=result.transaction_id,
            reason_codes=_aml_codes(result),
        )


def _map_aml(result: MonitorResult) -> ComplianceResult:
    if result.sanctions_block:
        return ComplianceResult.FAIL
    if result.requires_hitl:
        return ComplianceResult.ESCALATE
    return ComplianceResult.PASS


def _aml_codes(result: MonitorResult) -> tuple[str, ...]:
    flags = (
        ("SANCTIONS_BLOCK", result.sanctions_block),
        ("SAR_REQUIRED", result.sar_required),
        ("EDD_REQUIRED", result.edd_required),
        ("VELOCITY_DAILY", result.velocity_daily_breach),
        ("VELOCITY_MONTHLY", result.velocity_monthly_breach),
        ("STRUCTURING", result.structuring_signal),
    )
    return tuple(code for code, on in flags if on)


# ── Sanctions adapter (wraps services/sanctions_screening) ───────────────────


class SanctionsCheckAdapter:
    """Wrap an L3 ``ScreeningEngine`` as a :class:`SanctionsCheckPort`.

    The screening identity (name/nationality — PII) is resolved L3-side via the
    injected :class:`SanctionsIdentityPort`, so no PII flows through the producer
    core. Without a resolvable identity the check returns N/A (cannot screen)."""

    def __init__(
        self,
        engine: _ScreeningEngineLike,
        *,
        identity: SanctionsIdentityPort | None = None,
    ) -> None:
        self._engine = engine
        self._identity: SanctionsIdentityPort = identity or NullSanctionsIdentity()

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        identity = self._identity.resolve(request.subject_ref)
        if identity is None:
            return CheckOutcome(result=ComplianceResult.NA, ref="sanctions:no-identity")
        report = self._engine.screen_entity(
            entity_name=identity.entity_name,
            entity_type=identity.entity_type,
            nationality=identity.nationality,
        )
        return CheckOutcome(
            result=_map_sanctions(report.result),
            ref=report.report_id,
            reason_codes=tuple(sorted({hit.list_source for hit in report.hits})),
        )


def _map_sanctions(result: ScreeningResult) -> ComplianceResult:
    if result is ScreeningResult.CONFIRMED_MATCH:
        return ComplianceResult.FAIL
    if result in (ScreeningResult.POSSIBLE_MATCH, ScreeningResult.ERROR):
        return ComplianceResult.ESCALATE
    return ComplianceResult.PASS


# ── Fraud adapter (wraps services/fraud fraud_port) ──────────────────────────


class FraudCheckAdapter:
    """Wrap an L3 ``FraudScoringPort`` as a :class:`FraudCheckPort`."""

    def __init__(
        self,
        scorer: _FraudScorerLike,
        *,
        destination_country: str = "GB",
        payment_rail: str = "FPS",
    ) -> None:
        self._scorer = scorer
        self._country = destination_country
        self._rail = payment_rail

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        result = self._scorer.score(
            FraudScoringRequest(
                transaction_id=request.correlation_id,
                customer_id=request.subject_ref,
                amount=request.amount or Decimal("0"),
                currency=request.currency,
                destination_account="",
                destination_sort_code="",
                destination_country=self._country,
                payment_rail=self._rail,
                entity_type=request.entity_type,
            )
        )
        return CheckOutcome(
            result=_map_fraud(result),
            ref=result.transaction_id,
            reason_codes=(f"RISK_{result.risk.value}",),
        )


def _map_fraud(result: FraudScoringResult) -> ComplianceResult:
    if result.block:
        return ComplianceResult.FAIL
    if result.hold_for_review or result.app_scam_indicator.value != "NONE":
        return ComplianceResult.ESCALATE
    if result.risk.value in ("HIGH", "CRITICAL"):
        return ComplianceResult.ESCALATE
    return ComplianceResult.PASS


__all__ = [
    "AMLCheckAdapter",
    "FraudCheckAdapter",
    "SanctionsCheckAdapter",
]
