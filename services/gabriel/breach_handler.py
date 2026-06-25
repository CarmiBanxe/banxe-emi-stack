"""
services/gabriel/breach_handler.py
GabrielBreachHandler — BreachNotifyPort bridge to K-gabriel workflow.

D-recon spec §4: when ReconciliationEngine emits `safeguarding.breach.detected`
it fires this handler, which:
  1. Pre-registers the BreachEvent in the adapter (needed for BREACH_REPORT submit)
  2. Creates a DRAFT SubmissionRecord in ReturnsGovernor (HITL-gated; I-27)

HITL invariant (I-27): this handler only PROPOSES — no FCA submission is ever
made autonomously. The DRAFT must be approved by MLRO/CFO via ReturnsGovernor.approve().

Fail-open (per BreachNotifyPort spec): exceptions are logged, never raised,
so a notification failure never breaks the upstream reconciliation audit trail.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from services.recon.breach_notify_port import BreachEvent

logger = logging.getLogger(__name__)


# ── Minimal DI protocols ──────────────────────────────────────────────────────


@runtime_checkable
class BreachRegistrarPort(Protocol):
    """Minimal port for pre-registering a BreachEvent before BREACH_REPORT submit."""

    def register_breach_event(self, event: BreachEvent) -> None: ...


class _ReturnsGovernorPort(Protocol):
    """Minimal port for creating a breach DRAFT in the governor."""

    def create_breach_draft(self, breach_event: BreachEvent) -> object: ...


# ── Handler ───────────────────────────────────────────────────────────────────


class GabrielBreachHandler:
    """Implements BreachNotifyPort — bridges D-recon to K-gabriel (HITL-gated).

    On notify(event):
      1. Calls registrar.register_breach_event(event) so that if the draft is later
         approved, RegDataGabrielAdapter can build the FCA BreachRecord payload.
      2. Calls governor.create_breach_draft(event) to create a DRAFT in the
         ReturnsGovernor, awaiting HITL approval from MLRO/CFO.

    Errors from either call are logged and swallowed (fail-open), so a governor
    or adapter failure never aborts the parent reconciliation cycle.

    Args:
        governor: ReturnsGovernor instance (or any _ReturnsGovernorPort).
        registrar: Adapter that pre-registers events (BreachRegistrarPort).
    """

    def __init__(
        self,
        governor: _ReturnsGovernorPort,
        registrar: BreachRegistrarPort,
    ) -> None:
        self._governor = governor
        self._registrar = registrar

    def notify(self, event: BreachEvent) -> None:
        """Emit safeguarding.breach.detected into K-gabriel workflow.

        Fail-open: logs and returns on any error — never raises.
        """
        try:
            self._registrar.register_breach_event(event)
        except Exception as exc:
            logger.error(
                "GabrielBreachHandler: register_breach_event failed (recon_id=%s): %s",
                event.recon_id,
                exc,
            )
            return

        try:
            self._governor.create_breach_draft(event)
            logger.info(
                "GabrielBreachHandler: DRAFT created for recon_id=%s shortfall=%s %s",
                event.recon_id,
                event.shortfall,
                event.currency,
            )
        except Exception as exc:
            logger.error(
                "GabrielBreachHandler: create_breach_draft failed (recon_id=%s): %s",
                event.recon_id,
                exc,
            )
