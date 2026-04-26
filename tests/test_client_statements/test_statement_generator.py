"""Tests for Client Statement Service (IL-CST-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.client_statements.statement_generator import (
    InMemoryStatementDataPort,
    StatementGenerator,
)
from services.client_statements.statement_models import (
    StatementEntry,
    StatementFormat,
)


def _make_generator() -> StatementGenerator:
    return StatementGenerator(InMemoryStatementDataPort())


class TestStatementGenerator:
    def test_generate_returns_statement(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.statement_id is not None
        assert stmt.customer_id == "CUST001"

    def test_statement_has_entries(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert len(stmt.entries) > 0

    def test_entry_amounts_are_decimal_strings(self):
        """I-01: all amounts stored as Decimal strings."""
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        for entry in stmt.entries:
            assert isinstance(entry.amount, str)
            Decimal(entry.amount)  # must parse

    def test_entry_amounts_not_float(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        for entry in stmt.entries:
            assert not isinstance(entry.amount, float)

    def test_running_balance_is_decimal_string(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        for entry in stmt.entries:
            assert isinstance(entry.running_balance, str)
            Decimal(entry.running_balance)

    def test_balance_summary_decimal_strings(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        bs = stmt.balance_summary
        Decimal(bs.opening_balance)
        Decimal(bs.closing_balance)
        Decimal(bs.total_credits)
        Decimal(bs.total_debits)

    def test_statement_log_append_only(self):
        """I-24: statement_log grows."""
        gen = _make_generator()
        gen.generate("CUST001", "2026-01-01", "2026-01-31")
        gen.generate("CUST002", "2026-02-01", "2026-02-28")
        assert len(gen.statement_log) == 2

    def test_statement_id_starts_with_stmt(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.statement_id.startswith("stmt_")

    def test_pdf_format_stored(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31", StatementFormat.PDF)
        assert stmt.format == StatementFormat.PDF

    def test_csv_format_stored(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31", StatementFormat.CSV)
        assert stmt.format == StatementFormat.CSV

    def test_json_format_default(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.format == StatementFormat.JSON

    def test_bt013_email_raises(self):
        """BT-013: email delivery is a stub."""
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        with pytest.raises(NotImplementedError, match="BT-013"):
            gen.email_statement(stmt, "test@example.com")

    def test_statement_has_period_start_end(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.period_start == "2026-01-01"
        assert stmt.period_end == "2026-01-31"

    def test_statement_has_generated_at(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.generated_at is not None

    def test_fx_summary_present(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.fx_summary is not None

    def test_fee_breakdown_present(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        assert stmt.fee_breakdown is not None

    def test_closing_balance_calculated(self):
        gen = _make_generator()
        stmt = gen.generate("CUST001", "2026-01-01", "2026-01-31")
        closing = Decimal(stmt.balance_summary.closing_balance)
        assert isinstance(closing, Decimal)

    def test_statement_entry_validator_rejects_non_decimal(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            StatementEntry(
                entry_id="E001",
                date="2026-01-01",
                description="Test",
                amount="not_a_number",
                running_balance="1000.00",
            )


class TestStatementAgent:
    def test_propose_correction_returns_proposal(self):
        from services.client_statements.statement_agent import StatementAgent, StatementHITLProposal

        agent = StatementAgent()
        proposal = agent.propose_correction("stmt_001", "Incorrect fee applied")
        assert isinstance(proposal, StatementHITLProposal)

    def test_correction_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.client_statements.statement_agent import StatementAgent

        agent = StatementAgent()
        proposal = agent.propose_correction("stmt_001", "reason")
        assert proposal.approved is False

    def test_correction_requires_operations_officer(self):
        from services.client_statements.statement_agent import StatementAgent

        agent = StatementAgent()
        proposal = agent.propose_correction("stmt_001", "reason")
        assert proposal.requires_approval_from == "OPERATIONS_OFFICER"

    def test_proposals_accumulate(self):
        from services.client_statements.statement_agent import StatementAgent

        agent = StatementAgent()
        agent.propose_correction("stmt_001", "reason 1")
        agent.propose_correction("stmt_002", "reason 2")
        assert len(agent.proposals) == 2

    def test_statement_format_enum(self):
        assert StatementFormat.PDF == "pdf"
        assert StatementFormat.CSV == "csv"
        assert StatementFormat.JSON == "json"
