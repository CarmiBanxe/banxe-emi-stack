"""
rotation_audit_emitter.py — ROTATION_DUE / ROTATION_COMPLETED event emitter.

ADR-032 §Implementation-Plan item 2: emit canonical audit events for secret
rotation lifecycle into the ADR-027 BufferedAuditPort ring-buffer, from where
the existing drain cron flushes to ClickHouse safeguarding_audit.

Event shape (per ADR-032 §matrix):
  event_type:                  ROTATION_DUE | ROTATION_COMPLETED
  entity_id (audit_trail key): secret_type
  actor:                       "SecretRotation"
  payload:                     {secret_type, owner, previous_rotation_date,
                                next_due_date | completed_at, approved_by*,
                                cadence_days}
                              * COMPLETED only

severity:
  ROTATION_DUE       → WARNING (overdue rotation indicates compliance risk)
  ROTATION_COMPLETED → INFO    (terminal success record)

Pure delegation: this module builds AuditEvent dataclasses and forwards them
to BufferedAuditPort.record(). The buffer port already swallows internal
errors (ADR-027 §record never raises), so no additional exception handling
is layered here.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import time
from typing import TYPE_CHECKING

from src.safeguarding.audit_trail import AuditEvent

if TYPE_CHECKING:
    from src.safeguarding.buffered_audit_port import BufferedAuditPort


EVENT_ROTATION_DUE = "ROTATION_DUE"
EVENT_ROTATION_COMPLETED = "ROTATION_COMPLETED"
_ACTOR = "SecretRotation"


class RotationAuditEmitter:
    """Build and forward ROTATION_DUE / ROTATION_COMPLETED audit events."""

    def __init__(
        self,
        audit_port: BufferedAuditPort,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._audit = audit_port
        self._clock = clock

    def emit_rotation_due(
        self,
        secret_type: str,
        owner: str,
        previous_rotation_date: str | None,
        next_due_date: str,
        cadence_days: int,
    ) -> None:
        event = AuditEvent(
            event_type=EVENT_ROTATION_DUE,
            entity_id=secret_type,
            actor=_ACTOR,
            payload={
                "secret_type": secret_type,
                "owner": owner,
                "previous_rotation_date": previous_rotation_date,
                "next_due_date": next_due_date,
                "cadence_days": cadence_days,
            },
            severity="WARNING",
            occurred_at=datetime.fromtimestamp(self._clock(), tz=UTC),
        )
        self._audit.record(event)

    def emit_rotation_completed(
        self,
        secret_type: str,
        owner: str,
        approved_by: str,
        previous_rotation_date: str | None,
        completed_at: str,
        cadence_days: int,
    ) -> None:
        event = AuditEvent(
            event_type=EVENT_ROTATION_COMPLETED,
            entity_id=secret_type,
            actor=_ACTOR,
            payload={
                "secret_type": secret_type,
                "owner": owner,
                "approved_by": approved_by,
                "previous_rotation_date": previous_rotation_date,
                "completed_at": completed_at,
                "cadence_days": cadence_days,
            },
            severity="INFO",
            occurred_at=datetime.fromtimestamp(self._clock(), tz=UTC),
        )
        self._audit.record(event)
