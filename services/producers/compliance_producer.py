"""
services/producers/compliance_producer.py — ComplianceProducer (S5.2, ADR-046).

Closes audit gap #6: the L2 agents accept ``compliance_result`` defaulting to
:data:`ComplianceResult.PASS`; nothing produced a real verdict (silent
default-PASS = audit risk). :class:`ComplianceProducer` PRODUCES the verdict by
orchestrating the existing L3 through three INJECTED ports — an AML check
(wraps services/aml), a sanctions check (wraps services/sanctions_screening) and
a fraud check (wraps services/fraud). It NEVER imports or edits L3; the ports
default to Null producers (PASS) so it is unit-testable without live L3.

Aggregation (net verdict, ADR-046):
  • any FAIL                       → FAIL    (hard block, e.g. sanctions confirmed)
  • else any ESCALATE              → ESCALATE (e.g. AML SAR/EDD needing MLRO)
  • else all checks N/A            → N/A     (nothing applicable)
  • else                           → PASS

R-SEC: the returned :class:`ComplianceVerdict` carries the net result + per-check
opaque refs/codes only — never raw PII.
"""

from __future__ import annotations

from dataclasses import dataclass

from services.agents._lineage import ComplianceResult
from services.producers.ports import (
    AMLCheckPort,
    CheckOutcome,
    ComplianceCheckRequest,
    FraudCheckPort,
    NullAMLCheck,
    NullFraudCheck,
    NullSanctionsCheck,
    SanctionsCheckPort,
)


@dataclass(frozen=True)
class ComplianceVerdict:
    """Net compliance verdict + the per-check opaque outcomes (no PII).

    ``result`` is the value the composition root passes into an agent's
    ``compliance_result`` keyword param, REPLACING the default-PASS.
    """

    result: ComplianceResult
    correlation_id: str
    checks: tuple[CheckOutcome, ...]


def aggregate(outcomes: tuple[CheckOutcome, ...]) -> ComplianceResult:
    """Combine per-check outcomes into one net :class:`ComplianceResult`.

    FAIL dominates ESCALATE dominates PASS; an all-N/A set stays N/A.
    """
    results = [o.result for o in outcomes]
    if ComplianceResult.FAIL in results:
        return ComplianceResult.FAIL
    if ComplianceResult.ESCALATE in results:
        return ComplianceResult.ESCALATE
    if results and all(r is ComplianceResult.NA for r in results):
        return ComplianceResult.NA
    return ComplianceResult.PASS


class ComplianceProducer:
    """Produce a real :class:`ComplianceResult` by orchestrating injected L3 ports.

    Defaults to Null ports (all PASS) so the core is testable without live L3;
    the WIRED composition injects real adapters (``services/producers/adapters.py``).
    """

    def __init__(
        self,
        *,
        aml: AMLCheckPort | None = None,
        sanctions: SanctionsCheckPort | None = None,
        fraud: FraudCheckPort | None = None,
    ) -> None:
        self._aml: AMLCheckPort = aml or NullAMLCheck()
        self._sanctions: SanctionsCheckPort = sanctions or NullSanctionsCheck()
        self._fraud: FraudCheckPort = fraud or NullFraudCheck()

    def evaluate(self, request: ComplianceCheckRequest) -> ComplianceVerdict:
        """Run all three checks and return the aggregated verdict."""
        outcomes: tuple[CheckOutcome, ...] = (
            self._sanctions.check(request),
            self._aml.check(request),
            self._fraud.check(request),
        )
        return ComplianceVerdict(
            result=aggregate(outcomes),
            correlation_id=request.correlation_id,
            checks=outcomes,
        )


__all__ = ["ComplianceProducer", "ComplianceVerdict", "aggregate"]
