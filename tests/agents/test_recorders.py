"""Tests for the concrete DecisionRecorder sinks + the selection seam (FU-2).

Covers:
* ``InMemoryDecisionRecorder`` — record + query (the unchanged default).
* ``get_decision_recorder`` — default/inmemory/clickhouse/invalid selection.
* ``ClickHouseDecisionRecorder`` — serialise → insert and query → deserialise
  round-trip against an in-process fake client (no live ClickHouse needed).
* A live ClickHouse round-trip gated on ``DECISION_RECORDER_TEST_DSN`` so CI
  stays green where ClickHouse is not configured.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os

import pytest

from services.agents._lineage import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    DecisionRecorder,
)
from services.agents.recorders import (
    _COLUMNS,
    ClickHouseDecisionRecorder,
    InMemoryDecisionRecorder,
    _from_row,
    _to_row,
    get_decision_recorder,
)


def _record(**overrides: object) -> AgentDecisionRecord:
    base: dict[str, object] = {
        "record_id": "r-1",
        "timestamp": datetime(2026, 6, 14, 12, 0, 0, tzinfo=UTC),
        "agent_id": "kyc-onboarding",
        "triggering_event": "client.kyc.submitted",
        "intent": "verify_identity",
        "policies_evaluated": ["MLR-2017-18", "ADR-046"],
        "compliance_result": ComplianceResult.PASS,
        "reasoning_summary": "all checks passed",
        "confidence_score": 0.97,
        "action_taken": "approve",
        "human_reviewed_by": None,
        "correlation_id": "corr-abc",
        "cost_tokens": 1200,
        "cost_amount": Decimal("0.004200000000000000"),
        "budget_window_ref": "kyc-onboarding:default",
        "budget_breach_flag": BudgetBreach.NONE,
    }
    base.update(overrides)
    return AgentDecisionRecord(**base)  # type: ignore[arg-type]


# ── InMemoryDecisionRecorder (the unchanged default) ──────────────────────────


async def test_inmemory_records_and_queries_newest_first() -> None:
    rec = InMemoryDecisionRecorder()
    await rec.record(_record(record_id="r-1"))
    await rec.record(_record(record_id="r-2"))
    out = rec.query()
    assert [r.record_id for r in out] == ["r-2", "r-1"]


async def test_inmemory_query_filters_and_limit() -> None:
    rec = InMemoryDecisionRecorder()
    await rec.record(_record(record_id="r-1", agent_id="a", correlation_id="c1"))
    await rec.record(_record(record_id="r-2", agent_id="b", correlation_id="c2"))
    await rec.record(_record(record_id="r-3", agent_id="a", correlation_id="c2"))
    assert [r.record_id for r in rec.query(agent_id="a")] == ["r-3", "r-1"]
    assert [r.record_id for r in rec.query(correlation_id="c2")] == ["r-3", "r-2"]
    assert [r.record_id for r in rec.query(agent_id="a", limit=1)] == ["r-3"]


def test_inmemory_is_a_decision_recorder() -> None:
    assert isinstance(InMemoryDecisionRecorder(), DecisionRecorder)


# ── Selection seam ────────────────────────────────────────────────────────────


def test_get_decision_recorder_defaults_to_inmemory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DECISION_RECORDER", raising=False)
    assert isinstance(get_decision_recorder(), InMemoryDecisionRecorder)


@pytest.mark.parametrize("value", ["inmemory", "InMemory", "  inmemory  "])
def test_get_decision_recorder_inmemory(value: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_RECORDER", value)
    assert isinstance(get_decision_recorder(), InMemoryDecisionRecorder)


def test_get_decision_recorder_clickhouse(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_RECORDER", "clickhouse")
    # Inject a fake client so no driver/socket is touched at selection time.
    rec = get_decision_recorder(client=_FakeClickHouseClient())
    assert isinstance(rec, ClickHouseDecisionRecorder)


def test_get_decision_recorder_invalid_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DECISION_RECORDER", "postgres")
    with pytest.raises(ValueError, match="invalid"):
        get_decision_recorder()


# ── ClickHouseDecisionRecorder against a fake client ──────────────────────────


class _FakeClickHouseClient:
    """In-process stand-in for the ClickHouse driver client.

    Stores inserted rows as tuples in ``_COLUMNS`` order and serves ``query`` by
    applying the named params the recorder passes — enough to exercise the full
    serialise → insert and query → deserialise round-trip without ClickHouse.
    """

    def __init__(self) -> None:
        self.rows: list[tuple] = []
        self.last_insert_sql: str | None = None
        self.last_query_sql: str | None = None

    def insert(self, query: str, row: dict[str, object]) -> None:
        self.last_insert_sql = query
        self.rows.append(tuple(row[c] for c in _COLUMNS))

    def query(self, query: str, params: dict[str, object] | None = None) -> list[tuple]:
        self.last_query_sql = query
        params = params or {}
        idx = {c: i for i, c in enumerate(_COLUMNS)}
        out = [
            r
            for r in self.rows
            if ("agent_id" not in params or r[idx["agent_id"]] == params["agent_id"])
            and (
                "correlation_id" not in params
                or r[idx["correlation_id"]] == params["correlation_id"]
            )
        ]
        return list(reversed(out))


async def test_clickhouse_insert_serialises_record() -> None:
    client = _FakeClickHouseClient()
    rec = ClickHouseDecisionRecorder(client=client)
    await rec.record(_record(record_id="r-1", human_reviewed_by="MLRO-7"))
    assert client.last_insert_sql is not None
    assert client.last_insert_sql.startswith("INSERT INTO banxe.decision_records")
    stored = dict(zip(_COLUMNS, client.rows[0], strict=True))
    assert stored["record_id"] == "r-1"
    assert stored["human_reviewed_by"] == "MLRO-7"
    assert stored["human_override_flag"] == 1  # derived from human_reviewed_by
    assert stored["compliance_result"] == "PASS"
    assert stored["budget_breach_flag"] == "NONE"
    assert stored["policies_evaluated"] == ["MLR-2017-18", "ADR-046"]


async def test_clickhouse_round_trip_query() -> None:
    client = _FakeClickHouseClient()
    rec = ClickHouseDecisionRecorder(client=client)
    await rec.record(_record(record_id="r-1", agent_id="a", correlation_id="c1"))
    await rec.record(_record(record_id="r-2", agent_id="b", correlation_id="c1"))

    by_agent = rec.query(agent_id="a")
    assert [r.record_id for r in by_agent] == ["r-1"]
    assert isinstance(by_agent[0], AgentDecisionRecord)
    assert by_agent[0].compliance_result is ComplianceResult.PASS
    assert by_agent[0].budget_breach_flag is BudgetBreach.NONE
    assert by_agent[0].cost_amount == Decimal("0.004200000000000000")

    by_corr = rec.query(correlation_id="c1")
    assert {r.record_id for r in by_corr} == {"r-1", "r-2"}


def test_to_from_row_round_trip_preserves_fields() -> None:
    rec = _record(
        human_reviewed_by="DPO-2",
        escalated_to="MLRO",
        immutable_storage_ref="worm://lineage/r-1",
        input_tokens=800,
        output_tokens=400,
        budget_breach_flag=BudgetBreach.WARN,
        compliance_result=ComplianceResult.ESCALATE,
    )
    row = tuple(_to_row(rec)[c] for c in _COLUMNS)
    back = _from_row(row)
    assert back == rec


# ── Live ClickHouse round-trip (opt-in) ───────────────────────────────────────

_LIVE_DSN = os.environ.get("DECISION_RECORDER_TEST_DSN")


@pytest.mark.skipif(
    not _LIVE_DSN,
    reason="Set DECISION_RECORDER_TEST_DSN to run the live ClickHouse round-trip",
)
async def test_clickhouse_live_round_trip() -> None:  # pragma: no cover - opt-in only
    from services.agents.recorders import _DriverClickHouseClient

    client = _DriverClickHouseClient()
    rec = ClickHouseDecisionRecorder(client=client)
    unique = _record(record_id="live-" + datetime.now(UTC).isoformat(), correlation_id="live-corr")
    await rec.record(unique)
    out = rec.query(correlation_id="live-corr", limit=10)
    assert any(r.record_id == unique.record_id for r in out)
