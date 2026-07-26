"""services/client_statements/statement_adapter.py — StatementAdapter: the concrete
StatementPort implementation (ADR-055 §D2/§D3 — "the adapter wiring is a later sprint").

WHY THIS FILE EXISTS
--------------------
`StatementPort` (statement_port.py) is a CONTRACT only; `StatementGenerator` /
`StatementAgent` (statement_generator.py / statement_agent.py, the L4 HITL-correction
agent) are the pre-existing, untouched domain implementation. Nothing wired them
together. This module is that adapter — it implements ONLY the `StatementPort`
interface, delegating every read/generate/deliver operation to the existing domain
generator. It contains NO mask/gate/compliance logic: that governance layer is
`StatementClientAgent` (services/agents/statement_agent.py), which sits IN FRONT of
this adapter via the port interface (constructor injection) — see
services/client_statements/wiring.py for how the two are assembled together.

KNOWN, DOCUMENTED LIMITATIONS (not silently papered over)
-----------------------------------------------------------
1. `StatementGenerator` has no native "get by id" — only an append-only
   `statement_log` of summary dicts. This adapter keeps its own in-memory
   `statement_id -> Statement` cache, populated at generation time, to satisfy
   `get_statement`/`list_statements`/`deliver_statement`. A statement generated
   before this adapter's process started (e.g. by a different adapter instance)
   is NOT visible here — this is an in-process cache, not a persistence layer.
   Wiring a real persistence-backed data store is future work, not invented here.
2. `generate_statement` receives a `StatementPeriod` enum (MONTH/QUARTER/YEAR/CUSTOM),
   not explicit start/end dates — `GenerateStatementRequest` carries no date fields.
   This adapter interprets MONTH/QUARTER/YEAR as "start of the current period to
   today" (UTC). This is an explicit, documented interpretation, not an ADR-confirmed
   one — flag for operator/counsel review if a different convention (e.g. "most
   recently completed period") is actually required. CUSTOM has no date information
   anywhere in the request and is explicitly unsupported here (raises
   `StatementPortError`) rather than guessed.
3. `deliver_statement` has no destination-address parameter (no email/export target
   in the port signature). EMAIL/EXPORT therefore always resolve to
   `DeliveryStatus.PENDING_REVIEW` per ADR-055's documented channel classification —
   this adapter does not attempt to actually send/export, since it has no address to
   send to. Completing an approved external delivery (once a human reviewer supplies
   a destination) is a separate, future action, not implemented here. `ComplianceBlock`
   and `DeliveryEgressBlocked` are therefore never raised by this adapter today — there
   is no policy-driven blocking rule yet (the mask policy is still PROPOSED, see
   config/masks/statements-mask-policy.yaml); wiring one in is future work once real
   thresholds exist, not invented here.
4. `download_url` (the narrow additive `DeliveryResult` field, see statement_port.py)
   is populated only for DELIVERED (IN_APP) results, matching the synthetic path shape
   `api/routers/client_statements.py`'s pre-existing (ungoverned) `/download` endpoint
   already uses (`/files/statements/{statement_id}`) — no real file storage is wired
   here either; this preserves today's placeholder shape rather than inventing a new one.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from services.client_statements.statement_generator import StatementGenerator
from services.client_statements.statement_models import Statement
from services.client_statements.statement_models import StatementFormat as _DomainFormat
from services.client_statements.statement_port import (
    DeliveryChannel,
    DeliveryResult,
    DeliveryStatus,
    EntityId,
    GenerateStatementRequest,
    StatementDescriptor,
    StatementFormat,
    StatementId,
    StatementNotFound,
    StatementPeriod,
    StatementPort,
    StatementPortError,
    StatementView,
)


def _to_domain_format(port_format: StatementFormat) -> _DomainFormat:
    """Translate the port's StatementFormat into the domain's StatementFormat.

    The two enums share member names (PDF/CSV/JSON) but different string values
    (uppercase vs lowercase) — translate by name, not by value.
    """
    return _DomainFormat[port_format.name]


def _to_port_format(domain_format: _DomainFormat) -> StatementFormat:
    """Translate the domain's StatementFormat into the port's StatementFormat."""
    return StatementFormat[domain_format.name]


def _resolve_period_dates(period: StatementPeriod) -> tuple[str, str]:
    """Translate a StatementPeriod into concrete ISO date strings (see limitation #2).

    Interprets MONTH/QUARTER/YEAR as "start of the current period, to today" (UTC) —
    an explicit adapter-level interpretation, not an ADR-confirmed convention.

    Args:
        period: the requested statement period.

    Returns:
        (period_start, period_end) as ISO date strings.

    Raises:
        StatementPortError: `period` is CUSTOM — no date information exists anywhere
            in `GenerateStatementRequest` to resolve a custom range from.
    """
    today = datetime.now(UTC).date()
    if period == StatementPeriod.MONTH:
        start = today.replace(day=1)
    elif period == StatementPeriod.QUARTER:
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_start_month, 1)
    elif period == StatementPeriod.YEAR:
        start = date(today.year, 1, 1)
    else:
        raise StatementPortError(
            "StatementPeriod.CUSTOM is not supported: GenerateStatementRequest carries "
            "no explicit start/end dates to resolve it from (statement_adapter.py, "
            "module docstring limitation #2).",
            correlation_id="period_custom_unsupported",
        )
    return start.isoformat(), today.isoformat()


class StatementAdapter(StatementPort):
    """Concrete StatementPort implementation over the existing StatementGenerator.

    Constructor injection only (Protocol DI pattern, CLAUDE.md architecture rules) —
    contains no mask/gate/compliance logic; see the module docstring for the full
    division of responsibility against StatementClientAgent.
    """

    def __init__(self, generator: StatementGenerator | None = None) -> None:
        """Args:
            generator: the domain generator to delegate to; a fresh
                `StatementGenerator` (in-memory data port) is used if not supplied.
        """
        self._generator = generator or StatementGenerator()
        self._statements: dict[StatementId, Statement] = {}
        self._periods: dict[StatementId, StatementPeriod] = {}

    async def get_statement(self, statement_id: StatementId) -> StatementView:
        """Return a display-safe summary of a cached statement.

        Raises:
            StatementNotFound: `statement_id` was never generated by this adapter
                instance (see module docstring limitation #1).
        """
        stmt = self._statements.get(statement_id)
        if stmt is None:
            raise StatementNotFound(
                f"No statement cached for id {statement_id!r}",
                correlation_id=statement_id,
            )
        return self._to_view(stmt)

    async def list_statements(
        self,
        entity_id: EntityId,
        period: StatementPeriod,
    ) -> list[StatementDescriptor]:
        """List cached statements for `entity_id` matching `period` (read-only)."""
        return [
            StatementDescriptor(
                statement_id=stmt.statement_id,
                period=period,
                currency=stmt.balance_summary.currency,
                format=_to_port_format(stmt.format),
            )
            for stmt in self._statements.values()
            if stmt.customer_id == entity_id
            and self._periods.get(stmt.statement_id) == period
        ]

    async def generate_statement(
        self,
        request: GenerateStatementRequest,
    ) -> StatementView:
        """Generate a statement via the existing StatementGenerator (read-derived).

        Raises:
            StatementPortError: `request.period` is CUSTOM (see
                `_resolve_period_dates`).
        """
        period_start, period_end = _resolve_period_dates(request.period)
        stmt = self._generator.generate(
            customer_id=request.entity_id,
            period_start=period_start,
            period_end=period_end,
            fmt=_to_domain_format(request.format),
        )
        self._statements[stmt.statement_id] = stmt
        self._periods[stmt.statement_id] = request.period
        return self._to_view(stmt)

    async def deliver_statement(
        self,
        statement_id: StatementId,
        channel: DeliveryChannel,
    ) -> DeliveryResult:
        """Deliver a cached statement (ADR-055 data-egress gate; see limitation #3).

        IN_APP completes AUTO (DELIVERED) with a download_url. EMAIL/EXPORT always
        step to PENDING_REVIEW here — no destination address exists in the port
        signature to actually send/export to; completing an approved delivery is a
        separate future action.

        Raises:
            StatementNotFound: `statement_id` was never generated by this adapter
                instance.
        """
        stmt = self._statements.get(statement_id)
        if stmt is None:
            raise StatementNotFound(
                f"No statement cached for id {statement_id!r}",
                correlation_id=statement_id,
            )
        if channel == DeliveryChannel.IN_APP:
            return DeliveryResult(
                statement_id=statement_id,
                channel=channel,
                status=DeliveryStatus.DELIVERED,
                egress_redacted=True,
                download_url=f"/files/statements/{statement_id}",
            )
        return DeliveryResult(
            statement_id=statement_id,
            channel=channel,
            status=DeliveryStatus.PENDING_REVIEW,
            egress_redacted=True,
            download_url=None,
        )

    def _to_view(self, stmt: Statement) -> StatementView:
        """Build a StatementView from a cached domain Statement."""
        return StatementView(
            statement_id=stmt.statement_id,
            entity_id=stmt.customer_id,
            period=self._periods.get(stmt.statement_id, StatementPeriod.CUSTOM),
            opening_balance=Decimal(stmt.balance_summary.opening_balance),
            closing_balance=Decimal(stmt.balance_summary.closing_balance),
            line_count=len(stmt.entries),
            currency=stmt.balance_summary.currency,
            format=_to_port_format(stmt.format),
        )
