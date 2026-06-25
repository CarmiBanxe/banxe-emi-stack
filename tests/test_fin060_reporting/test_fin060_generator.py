"""
tests/test_fin060_reporting/test_fin060_generator.py — FIN060Generator tests
IL-FIN060-01 | Phase 51C | Sprint 36
≥20 tests covering generate, approve HITLProposal, BT-006 stub, dashboard, I-24 append
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.reporting.fin060_generator_v2 import FIN060Generator, HITLProposal
from services.reporting.report_models import InMemoryReportStore

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def store() -> InMemoryReportStore:
    return InMemoryReportStore()


@pytest.fixture
def generator(store: InMemoryReportStore) -> FIN060Generator:
    return FIN060Generator(store=store)


def make_ledger_entry(account_type: str, balance: str, currency: str = "GBP") -> dict:
    return {"account_type": account_type, "balance": balance, "currency": currency}


# ── generate_fin060 ───────────────────────────────────────────────────────────


def test_generate_fin060_returns_hitl_proposal(generator: FIN060Generator) -> None:
    result = generator.generate_fin060(4, 2026, [])
    assert isinstance(result, HITLProposal)


def test_generate_fin060_requires_cfo(generator: FIN060Generator) -> None:
    result = generator.generate_fin060(4, 2026, [])
    assert result.requires_approval_from == "CFO"


def test_generate_fin060_autonomy_l4(generator: FIN060Generator) -> None:
    result = generator.generate_fin060(4, 2026, [])
    assert result.autonomy_level == "L4"


def test_generate_fin060_action_field(generator: FIN060Generator) -> None:
    result = generator.generate_fin060(4, 2026, [])
    assert result.action == "generate_fin060"


def test_generate_fin060_entity_id_8chars(generator: FIN060Generator) -> None:
    result = generator.generate_fin060(4, 2026, [])
    assert len(result.entity_id) == 8


def test_generate_fin060_appends_to_store(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    generator.generate_fin060(4, 2026, [])
    assert len(store.list_reports()) == 1


def test_generate_fin060_report_is_draft(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    generator.generate_fin060(4, 2026, [])
    report = store.get_by_period(4, 2026)
    assert report is not None
    assert report.status == "DRAFT"


def test_generate_fin060_decimal_amounts(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    ledger_data = [
        make_ledger_entry("safeguarding", "100000.00"),
        make_ledger_entry("operational", "50000.00"),
    ]
    generator.generate_fin060(4, 2026, ledger_data)
    report = store.get_by_period(4, 2026)
    assert report is not None
    assert isinstance(report.total_safeguarded_gbp, Decimal)
    assert isinstance(report.total_operational_gbp, Decimal)


def test_generate_fin060_amounts_never_float(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    ledger_data = [make_ledger_entry("safeguarding", "100000.00")]
    generator.generate_fin060(4, 2026, ledger_data)
    report = store.get_by_period(4, 2026)
    assert report is not None
    assert not isinstance(report.total_safeguarded_gbp, float)


def test_generate_fin060_correct_safeguarded_total(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    ledger_data = [
        make_ledger_entry("safeguarding", "100000.00"),
        make_ledger_entry("safeguarding", "50000.00"),
    ]
    generator.generate_fin060(4, 2026, ledger_data)
    report = store.get_by_period(4, 2026)
    assert report is not None
    assert report.total_safeguarded_gbp == Decimal("150000.00")


def test_generate_fin060_invalid_month_raises(generator: FIN060Generator) -> None:
    with pytest.raises(ValueError, match="Invalid month"):
        generator.generate_fin060(13, 2026, [])


def test_generate_fin060_invalid_year_raises(generator: FIN060Generator) -> None:
    with pytest.raises(ValueError, match="Invalid year"):
        generator.generate_fin060(4, 2019, [])


def test_generate_fin060_multiple_months_append_only(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    for m in range(1, 4):
        generator.generate_fin060(m, 2026, [])
    assert len(store.list_reports()) == 3


# ── approve_report → HITLProposal ─────────────────────────────────────────────


def test_approve_report_returns_hitl_proposal(generator: FIN060Generator) -> None:
    proposal = generator.approve_report("report-123", "cfo_user")
    assert isinstance(proposal, HITLProposal)


def test_approve_report_requires_cfo(generator: FIN060Generator) -> None:
    proposal = generator.approve_report("report-123", "cfo_user")
    assert proposal.requires_approval_from == "CFO"


def test_approve_report_autonomy_l4(generator: FIN060Generator) -> None:
    proposal = generator.approve_report("report-123", "cfo_user")
    assert proposal.autonomy_level == "L4"


def test_approve_report_action_field(generator: FIN060Generator) -> None:
    proposal = generator.approve_report("report-123", "cfo_user")
    assert proposal.action == "approve_fin060"


# ── submit_to_regdata — L4 HITL proposal (I-27) ──────────────────────────────


def test_submit_to_regdata_returns_hitl_proposal(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-123")
    assert isinstance(proposal, HITLProposal)


def test_submit_to_regdata_requires_cfo(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-123")
    assert proposal.requires_approval_from == "CFO"


def test_submit_to_regdata_autonomy_l4(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-123")
    assert proposal.autonomy_level == "L4"


def test_submit_to_regdata_action_field(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-123")
    assert proposal.action == "submit_fin060_to_regdata"


def test_submit_to_regdata_reason_contains_report_id(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-abc-99")
    assert "report-abc-99" in proposal.reason


def test_submit_to_regdata_reason_mentions_cass15(generator: FIN060Generator) -> None:
    proposal = generator.submit_to_regdata("report-123")
    assert "CASS 15" in proposal.reason or "15.12" in proposal.reason


def test_submit_to_regdata_different_ids_have_different_entity_ids(
    generator: FIN060Generator,
) -> None:
    p1 = generator.submit_to_regdata("report-001")
    p2 = generator.submit_to_regdata("report-002")
    assert p1.entity_id != p2.entity_id


# ── get_dashboard ─────────────────────────────────────────────────────────────


def test_get_dashboard_returns_dict(generator: FIN060Generator) -> None:
    result = generator.get_dashboard()
    assert isinstance(result, dict)


def test_get_dashboard_total_reports_zero_initially(generator: FIN060Generator) -> None:
    result = generator.get_dashboard()
    assert result["total_reports"] == 0


def test_get_dashboard_safeguarded_gbp_is_string(generator: FIN060Generator) -> None:
    generator.generate_fin060(4, 2026, [make_ledger_entry("safeguarding", "100000.00")])
    result = generator.get_dashboard()
    # Decimal as string (I-01)
    assert isinstance(result["safeguarded_gbp"], str)


def test_get_dashboard_pending_approval_count(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    generator.generate_fin060(4, 2026, [])
    result = generator.get_dashboard()
    assert result["pending_approval"] == 1


def test_get_dashboard_total_reports_increments(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    generator.generate_fin060(1, 2026, [])
    generator.generate_fin060(2, 2026, [])
    result = generator.get_dashboard()
    assert result["total_reports"] == 2


def test_get_report_returns_none_for_missing(generator: FIN060Generator) -> None:
    result = generator.get_report(1, 2020)
    assert result is None


def test_get_report_returns_report_after_generate(
    generator: FIN060Generator, store: InMemoryReportStore
) -> None:
    generator.generate_fin060(4, 2026, [])
    report = generator.get_report(4, 2026)
    assert report is not None
    assert report.month == 4
    assert report.year == 2026
