"""Shared audit-trail emit for reconciliation breach decisions.

A small, regime-agnostic structured-audit primitive both safeguarding paths emit
through, so the breach-decision audit record has ONE shape. The regime label is an
input (``"CASS15"`` / ``"CASS7.15"``); the core never decides which regime it is.

R-SEC: the event carries the reconciliation MAGNITUDE (discrepancy / threshold) and
a recon REFERENCE only — never raw account balances or client PII. Money is
serialised as a Decimal string (I-01 / I-05), never float.

Emission is additive and side-effect-only: it changes no reconciliation status,
threshold, or report — it records what was already decided. A caller may inject an
:class:`AuditSink` (e.g. a ClickHouse writer) or fall back to structured logging.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging
from typing import Protocol

logger = logging.getLogger("banxe.recon_core.audit")


@dataclass(frozen=True)
class ReconAuditEvent:
    """Immutable, regime-agnostic reconciliation audit record."""

    regime: str  # injected regime label, e.g. "CASS15" | "CASS7.15"
    event_type: str  # e.g. "RECON_RESULT"
    recon_ref: str  # date / id reference — NOT raw balances (R-SEC)
    is_breach: bool
    breach_kind: str | None
    amount_gbp: str  # Decimal as string (I-05)
    threshold_gbp: str  # Decimal as string (I-05)
    detail: str = ""

    @classmethod
    def from_magnitude(
        cls,
        regime: str,
        recon_ref: str,
        is_breach: bool,
        breach_kind: str | None,
        amount: Decimal,
        threshold: Decimal,
        event_type: str = "RECON_RESULT",
        detail: str = "",
    ) -> ReconAuditEvent:
        """Build an event from Decimal magnitudes, serialising money to strings."""
        return cls(
            regime=regime,
            event_type=event_type,
            recon_ref=recon_ref,
            is_breach=is_breach,
            breach_kind=breach_kind,
            amount_gbp=str(amount),
            threshold_gbp=str(threshold),
            detail=detail,
        )


class AuditSink(Protocol):
    """Optional injection point for a durable audit writer (e.g. ClickHouse)."""

    def emit(self, event: ReconAuditEvent) -> None: ...


def emit_recon_audit(event: ReconAuditEvent, sink: AuditSink | None = None) -> ReconAuditEvent:
    """Emit a reconciliation audit event.

    Routes to the injected ``sink`` when provided; otherwise logs a structured line
    (WARNING for a breach, INFO otherwise). Fail-open: a sink error is logged and
    swallowed so audit emission can never block a reconciliation run. Returns the
    event for convenience/testing.
    """
    if sink is not None:
        try:
            sink.emit(event)
        except Exception as exc:  # fail-open — audit must not break recon
            logger.error("recon audit sink failed for %s: %s", event.recon_ref, exc)

    log_fn = logger.warning if event.is_breach else logger.info
    log_fn(
        "RECON_AUDIT regime=%s ref=%s breach=%s kind=%s amount=£%s threshold=£%s %s",
        event.regime,
        event.recon_ref,
        event.is_breach,
        event.breach_kind or "-",
        event.amount_gbp,
        event.threshold_gbp,
        event.detail,
    )
    return event
