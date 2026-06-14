"""Concrete :class:`DecisionRecorder` sinks + the selection seam (ADR-046).

WHY: ``services/agents/_lineage.py`` defines the :class:`DecisionRecorder` ABC
(the producer→sink seam) but deliberately leaves the sink unimplemented — the
masks depend only on the interface. This module supplies the two concrete sinks
and the composition seam that chooses between them:

* :class:`InMemoryDecisionRecorder` — the default. Append-only in-process list;
  exactly the behaviour the system has today (no ClickHouse dependency).
* :class:`ClickHouseDecisionRecorder` — a durable, queryable, regulatory-grade
  store backed by ``banxe.decision_records`` (infra/clickhouse/migrations/006).
  Strictly additive and OFF unless ``DECISION_RECORDER=clickhouse``.

* :func:`get_decision_recorder` — the selection factory. With no env var (or
  ``DECISION_RECORDER=inmemory``) it returns the in-memory sink, so the system
  behaves exactly as before. This is the composition seam the Intent Layer will
  call when it is later activated; INTENT_LAYER_ENABLED stays false for now.

R-SEC (ADR-021): only opaque governance metadata is persisted — never
seed/entropy/key/password/plaintext/ciphertext (see ``_lineage.py``).
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

from services.agents._lineage import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    DecisionRecorder,
)

logger = logging.getLogger(__name__)

# Column order shared by INSERT and SELECT — keep in lockstep with migration 006
# and with the AgentDecisionRecord → row mapping below.
_COLUMNS: tuple[str, ...] = (
    "record_id",
    "timestamp",
    "agent_id",
    "triggering_event",
    "intent",
    "policies_evaluated",
    "compliance_result",
    "reasoning_summary",
    "confidence_score",
    "action_taken",
    "correlation_id",
    "human_reviewed_by",
    "human_override_flag",
    "escalated_to",
    "cost_tokens",
    "cost_amount",
    "budget_window_ref",
    "budget_breach_flag",
    "input_tokens",
    "output_tokens",
    "immutable_storage_ref",
)

_TABLE = "banxe.decision_records"


# ── In-memory sink (default — behaviour unchanged) ────────────────────────────


class InMemoryDecisionRecorder(DecisionRecorder):
    """Append-only in-process sink (the system's current default behaviour).

    Records are kept in insertion order; :meth:`query` offers the same minimal
    read surface as the ClickHouse sink so callers can switch sinks transparently.
    """

    def __init__(self) -> None:
        self._records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self._records.append(record)

    def query(
        self,
        *,
        agent_id: str | None = None,
        correlation_id: str | None = None,
        limit: int | None = None,
    ) -> list[AgentDecisionRecord]:
        """Return recorded records, newest first, optionally filtered."""
        rows = [
            r
            for r in reversed(self._records)
            if (agent_id is None or r.agent_id == agent_id)
            and (correlation_id is None or r.correlation_id == correlation_id)
        ]
        return rows[:limit] if limit is not None else rows


# ── ClickHouse sink (flagged, additive) ───────────────────────────────────────


@runtime_checkable
class ClickHouseClient(Protocol):
    """Minimal seam over the ClickHouse driver (mirrors recon's client).

    Two operations are enough for an append-only lineage store: a row insert and
    a parameterised read. The default implementation wraps ``clickhouse_driver``;
    tests inject a fake conforming to this Protocol (no live ClickHouse needed).
    """

    def insert(self, query: str, row: dict[str, object]) -> None: ...

    def query(self, query: str, params: dict[str, object] | None = None) -> list[tuple]: ...


class _DriverClickHouseClient:
    """Production :class:`ClickHouseClient` over ``clickhouse_driver`` (lazy import).

    Connection details come from ``services.config`` (CLICKHOUSE_HOST/PORT/DB/
    USER/PASSWORD), exactly like ``services.recon.clickhouse_client`` — no
    connection logic is duplicated beyond constructing the shared driver client.
    """

    def __init__(self) -> None:
        from services.config import (
            CLICKHOUSE_DB,
            CLICKHOUSE_HOST,
            CLICKHOUSE_PASSWORD,
            CLICKHOUSE_PORT,
            CLICKHOUSE_USER,
        )

        try:
            import clickhouse_driver  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - exercised only without the driver
            raise RuntimeError(
                "clickhouse-driver is not installed. Run: pip install clickhouse-driver"
            ) from exc

        self._client = clickhouse_driver.Client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            database=CLICKHOUSE_DB,
            user=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )

    def insert(self, query: str, row: dict[str, object]) -> None:
        self._client.execute(query, [row])

    def query(self, query: str, params: dict[str, object] | None = None) -> list[tuple]:
        return self._client.execute(query, params or {})


def _to_row(record: AgentDecisionRecord) -> dict[str, object]:
    """Serialise an AgentDecisionRecord into a ``decision_records`` row dict."""
    return {
        "record_id": record.record_id,
        "timestamp": record.timestamp,
        "agent_id": record.agent_id,
        "triggering_event": record.triggering_event,
        "intent": record.intent,
        "policies_evaluated": list(record.policies_evaluated),
        "compliance_result": str(record.compliance_result),
        "reasoning_summary": record.reasoning_summary,
        "confidence_score": record.confidence_score,
        "action_taken": record.action_taken,
        "correlation_id": record.correlation_id,
        "human_reviewed_by": record.human_reviewed_by,
        "human_override_flag": 1 if record.human_reviewed_by else 0,
        "escalated_to": record.escalated_to,
        "cost_tokens": record.cost_tokens,
        "cost_amount": record.cost_amount,
        "budget_window_ref": record.budget_window_ref,
        "budget_breach_flag": str(record.budget_breach_flag),
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "immutable_storage_ref": record.immutable_storage_ref,
    }


def _from_row(row: tuple) -> AgentDecisionRecord:
    """Rebuild an AgentDecisionRecord from a SELECT row (columns in _COLUMNS order)."""
    v = dict(zip(_COLUMNS, row, strict=True))
    return AgentDecisionRecord(
        record_id=v["record_id"],
        timestamp=v["timestamp"],
        agent_id=v["agent_id"],
        triggering_event=v["triggering_event"],
        intent=v["intent"],
        policies_evaluated=list(v["policies_evaluated"]),
        compliance_result=ComplianceResult(v["compliance_result"]),
        reasoning_summary=v["reasoning_summary"],
        confidence_score=v["confidence_score"],
        action_taken=v["action_taken"],
        human_reviewed_by=v["human_reviewed_by"],
        correlation_id=v["correlation_id"],
        cost_tokens=v["cost_tokens"],
        cost_amount=v["cost_amount"],
        budget_window_ref=v["budget_window_ref"],
        budget_breach_flag=BudgetBreach(v["budget_breach_flag"]),
        escalated_to=v["escalated_to"],
        immutable_storage_ref=v["immutable_storage_ref"],
        input_tokens=v["input_tokens"],
        output_tokens=v["output_tokens"],
    )


class ClickHouseDecisionRecorder(DecisionRecorder):
    """Durable, queryable lineage sink backed by ``banxe.decision_records``.

    The client is injected for testability; when omitted, a lazily-built
    :class:`_DriverClickHouseClient` reads connection details from the shared
    ClickHouse env/config. Construction never opens a socket until the first
    insert/query, so the failure mode is a clear runtime error at first use.
    """

    def __init__(self, client: ClickHouseClient | None = None) -> None:
        self._client = client
        self._insert_sql = (
            f"INSERT INTO {_TABLE} (" + ", ".join(_COLUMNS) + ") VALUES"
        )

    def _ch(self) -> ClickHouseClient:
        if self._client is None:
            self._client = _DriverClickHouseClient()
        return self._client

    async def record(self, record: AgentDecisionRecord) -> None:
        self._ch().insert(self._insert_sql, _to_row(record))
        logger.debug("decision_records insert: record_id=%s agent=%s", record.record_id, record.agent_id)

    def query(
        self,
        *,
        agent_id: str | None = None,
        correlation_id: str | None = None,
        limit: int = 100,
    ) -> list[AgentDecisionRecord]:
        """Read lineage back, newest first, filtered by agent_id and/or correlation_id."""
        where: list[str] = []
        params: dict[str, object] = {}
        if agent_id is not None:
            where.append("agent_id = %(agent_id)s")
            params["agent_id"] = agent_id
        if correlation_id is not None:
            where.append("correlation_id = %(correlation_id)s")
            params["correlation_id"] = correlation_id
        clause = (" WHERE " + " AND ".join(where)) if where else ""
        cols = ", ".join(_COLUMNS)
        # nosec B608 — every interpolated part is a module constant (_COLUMNS,
        # _TABLE, fixed WHERE fragments) or an int-cast; row values are bound via
        # named params, never interpolated.
        sql = f"SELECT {cols} FROM {_TABLE}{clause} ORDER BY timestamp DESC LIMIT {int(limit)}"  # noqa: S608, E501
        return [_from_row(r) for r in self._ch().query(sql, params)]


# ── Selection seam ────────────────────────────────────────────────────────────


def get_decision_recorder(client: ClickHouseClient | None = None) -> DecisionRecorder:
    """Select the lineage sink from the ``DECISION_RECORDER`` env var.

    ``inmemory`` (default, or unset) → :class:`InMemoryDecisionRecorder`; the
    system behaves exactly as today. ``clickhouse`` →
    :class:`ClickHouseDecisionRecorder`. Any other value raises (fail-closed) so
    a typo can never silently fall back to a different durability guarantee.

    NOTE: this is the composition seam only — selecting the sink does NOT enable
    the Intent Layer. INTENT_LAYER_ENABLED stays false until a later FU.
    """
    choice = os.environ.get("DECISION_RECORDER", "inmemory").strip().lower()
    if choice == "inmemory":
        return InMemoryDecisionRecorder()
    if choice == "clickhouse":
        return ClickHouseDecisionRecorder(client=client)
    raise ValueError(
        f"DECISION_RECORDER={choice!r} is invalid; expected 'inmemory' or 'clickhouse'"
    )


__all__ = [
    "ClickHouseClient",
    "ClickHouseDecisionRecorder",
    "InMemoryDecisionRecorder",
    "get_decision_recorder",
]
