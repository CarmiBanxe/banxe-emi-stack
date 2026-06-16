"""
services/producers/ports.py — injected seams + non-PII value objects for the
compliance / confidence / cost PRODUCERS (S5.2, ADR-046 / ADR-047 / ADR-049).

WHY THIS FILE EXISTS
--------------------
The 9 L2 client-facing agents accept ``compliance_result``, ``confidence_score``
and ``request_cost`` as INJECTED keyword-only inputs, with
``compliance_result`` defaulting to :data:`ComplianceResult.PASS` (audit gap #6:
nothing PRODUCES the verdict — a silent default-PASS is an audit risk). This
package is the producer side of that seam: the composition root computes the
three values and passes them in, so the agents need NO edits.

These producers WRAP the real L3 (services/aml, services/sanctions_screening,
services/fraud) through the Protocol ports defined here — they never import the
concrete L3 classes, so the core is unit-testable with the Null defaults below
(no live L3, no network). The WIRED composition supplies real adapters
(``services/producers/adapters.py``).

R-SEC (R-SEC-NEW-01, ADR-021): every type that crosses this seam carries only
opaque identifiers + risk-relevant scalars and verdict codes — NEVER a name, an
account number, or any raw PII. PII stays L3-side; it is resolved into a check
only inside an adapter, behind :class:`SanctionsIdentityPort`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from services.agents._lineage import (
    BudgetBreach,
    ComplianceResult,
    CostCap,
    RequestCost,
)

# ── Non-PII value objects crossing the producer seam ─────────────────────────


@dataclass(frozen=True)
class ComplianceCheckRequest:
    """Normalised, NON-PII input for a compliance check.

    Carries only an opaque subject handle plus risk-relevant scalars. The
    ``subject_ref`` is a tokenised/opaque customer handle — never a name. The
    sanctions identity (name/nationality) is resolved L3-side inside the adapter
    via :class:`SanctionsIdentityPort`, never threaded through this object.
    """

    action: str  # the resolved intent / capability / action id
    correlation_id: str
    subject_ref: str  # opaque customer handle — NEVER a name / PII
    amount: Decimal = Decimal("0")
    currency: str = "GBP"
    entity_type: str = "INDIVIDUAL"  # "INDIVIDUAL" | "COMPANY"
    is_pep: bool = False
    is_sanctions_hit: bool = False  # pre-resolved upstream flag (opaque)
    is_fx: bool = False
    risk_class: str = "STANDARD"  # STANDARD | ELEVATED | HIGH


@dataclass(frozen=True)
class CheckOutcome:
    """One L3 check's verdict, reduced to a :class:`ComplianceResult` + opaque refs.

    ``ref`` is an opaque L3 handle (report/decision id). ``reason_codes`` are
    non-PII policy codes (e.g. ``SAR_REQUIRED``, ``SANCTIONS_CONFIRMED``) — never
    raw L3 reason strings, which may embed amounts/identities (R-SEC).
    """

    result: ComplianceResult
    ref: str = ""
    reason_codes: tuple[str, ...] = ()


# ── Compliance L3 check ports (wrapped by adapters, defaulted to Null) ────────


@runtime_checkable
class AMLCheckPort(Protocol):
    """Wraps services/aml (tx_monitor + thresholds). Returns an opaque verdict."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome: ...


@runtime_checkable
class SanctionsCheckPort(Protocol):
    """Wraps services/sanctions_screening. Returns an opaque verdict."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome: ...


@runtime_checkable
class FraudCheckPort(Protocol):
    """Wraps services/fraud (fraud_port). Returns an opaque verdict."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome: ...


@runtime_checkable
class SanctionsIdentityPort(Protocol):
    """PII boundary owned by the composition root: resolves an opaque
    ``subject_ref`` to the screening identity needed by the L3 engine. Kept OUT
    of :class:`ComplianceCheckRequest` so no raw PII ever flows through the
    producer core (R-SEC)."""

    def resolve(self, subject_ref: str) -> SanctionsIdentity | None: ...


@dataclass(frozen=True)
class SanctionsIdentity:
    """Screening identity resolved L3-side only (held by the wiring layer)."""

    entity_name: str
    entity_type: str  # "individual" | "organisation" | "vessel"
    nationality: str  # ISO-3166-1 alpha-2


# ── Cost source port (S1 gateway per-key accounting, defaulted to static) ─────


@runtime_checkable
class CostSourcePort(Protocol):
    """Live per-key usage from the S1 gateway accounting (ADR-047). Returns
    ``None`` when no live accounting is available — the estimator then falls back
    to a deterministic static estimate."""

    def usage_for(self, accounting_key: str) -> RequestCost | None: ...


# ── Null / static defaults — make the core testable without live L3 ──────────


class NullAMLCheck:
    """Default AML port: no live L3 → PASS. Replaced by a real adapter when wired."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        return CheckOutcome(result=ComplianceResult.PASS, ref="aml:null")


class NullSanctionsCheck:
    """Default sanctions port: no live L3 → PASS. Replaced when wired."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        return CheckOutcome(result=ComplianceResult.PASS, ref="sanctions:null")


class NullFraudCheck:
    """Default fraud port: no live L3 → PASS. Replaced when wired."""

    def check(self, request: ComplianceCheckRequest) -> CheckOutcome:
        return CheckOutcome(result=ComplianceResult.PASS, ref="fraud:null")


class NullSanctionsIdentity:
    """Default identity resolver: no PII map wired → cannot screen → ``None``."""

    def resolve(self, subject_ref: str) -> SanctionsIdentity | None:
        return None


class StaticCostSource:
    """Default cost source: no live S1 accounting → deterministic static estimate."""

    def usage_for(self, accounting_key: str) -> RequestCost | None:
        return None


# Default cost cap used by ``ProducerBundle.null`` and as a safe fallback
# (ADR-047 §D2 — token + Decimal, no float).
DEFAULT_COST_CAP = CostCap(
    max_request_tokens=8_000,
    max_request_cost=Decimal("0.50"),
    max_window_tokens=2_000_000,
    max_window_cost=Decimal("100.00"),
)

# Default per-1k-token price for the static estimate (Decimal — never float).
DEFAULT_PRICE_PER_1K_TOKENS = Decimal("0.015")

__all__ = [
    "DEFAULT_COST_CAP",
    "DEFAULT_PRICE_PER_1K_TOKENS",
    "AMLCheckPort",
    "BudgetBreach",
    "CheckOutcome",
    "ComplianceCheckRequest",
    "CostSourcePort",
    "FraudCheckPort",
    "NullAMLCheck",
    "NullFraudCheck",
    "NullSanctionsCheck",
    "NullSanctionsIdentity",
    "SanctionsCheckPort",
    "SanctionsIdentity",
    "SanctionsIdentityPort",
    "StaticCostSource",
]
