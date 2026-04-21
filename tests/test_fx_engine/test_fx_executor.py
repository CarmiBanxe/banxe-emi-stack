"""
Tests for FX Executor.
IL-FXE-01 | Sprint 34 | Phase 48
Tests: execute <£10k auto, ≥£10k HITLProposal (I-04/I-27), expired quote → EXPIRED, reject HITL
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.fx_engine.fx_executor import LARGE_FX_THRESHOLD, FXExecutor
from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.models import (
    ExecutionStatus,
    FXExecution,
    HITLProposal,
    InMemoryExecutionStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
    QuoteStatus,
)


@pytest.fixture
def quote_store():
    return InMemoryQuoteStore()


@pytest.fixture
def executor(quote_store):
    exec_store = InMemoryExecutionStore()
    return FXExecutor(quote_store=quote_store, execution_store=exec_store)


@pytest.fixture
def quoter(quote_store):
    return FXQuoter(rate_store=InMemoryRateStore(), quote_store=quote_store)


class TestExecuteSmallAmount:
    def test_execute_below_10k_confirmed(self, executor, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("1000"), "GBP")
        result = executor.execute(quote.quote_id, "test_user")
        assert isinstance(result, FXExecution)
        assert result.status == ExecutionStatus.CONFIRMED

    def test_execute_below_10k_has_execution_id(self, executor, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("5000"), "GBP")
        result = executor.execute(quote.quote_id, "test_user")
        assert isinstance(result, FXExecution)
        assert result.execution_id.startswith("exe_")

    def test_execute_below_10k_has_timestamp(self, executor, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("500"), "GBP")
        result = executor.execute(quote.quote_id, "test_user")
        assert isinstance(result, FXExecution)
        assert result.executed_at is not None

    def test_execute_updates_quote_status(self, executor, quoter, quote_store):
        quote = quoter.create_quote("GBP/EUR", Decimal("2000"), "GBP")
        executor.execute(quote.quote_id, "user")
        updated = quote_store.get(quote.quote_id)
        assert updated.status == QuoteStatus.EXECUTED


class TestExecuteLargeAmount:
    def test_execute_at_10k_returns_hitl(self, executor, quoter):
        # We need to create a quote that matches £10k threshold
        # The quoter uses GBP/EUR rate, so 10000 GBP sell
        store = InMemoryQuoteStore()
        from services.fx_engine.models import FXQuote

        quote = FXQuote(
            quote_id="qte_large",
            currency_pair="GBP/EUR",
            sell_amount=Decimal("10000"),
            sell_currency="GBP",
            buy_amount=Decimal("11615"),
            buy_currency="EUR",
            rate=Decimal("1.1615"),
            spread=Decimal("0.005"),
            created_at=datetime.now(UTC).isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        )
        store.save(quote)
        exec_store = InMemoryExecutionStore()
        ex = FXExecutor(quote_store=store, execution_store=exec_store)
        result = ex.execute("qte_large", "user")
        assert isinstance(result, HITLProposal)

    def test_execute_above_10k_hitl_l4(self, executor, quoter):
        store = InMemoryQuoteStore()
        from services.fx_engine.models import FXQuote

        quote = FXQuote(
            quote_id="qte_xlarge",
            currency_pair="GBP/EUR",
            sell_amount=Decimal("50000"),
            sell_currency="GBP",
            buy_amount=Decimal("58000"),
            buy_currency="EUR",
            rate=Decimal("1.16"),
            spread=Decimal("0.003"),
            created_at=datetime.now(UTC).isoformat(),
            expires_at=(datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        )
        store.save(quote)
        ex = FXExecutor(quote_store=store, execution_store=InMemoryExecutionStore())
        result = ex.execute("qte_xlarge", "user")
        assert isinstance(result, HITLProposal)
        assert result.autonomy_level == "L4"
        assert result.requires_approval_from == "TREASURY_OPS"

    def test_large_fx_threshold_10k(self):
        assert Decimal("10000") == LARGE_FX_THRESHOLD


class TestExecuteExpiredQuote:
    def test_expired_quote_returns_expired_execution(self, executor):
        store = InMemoryQuoteStore()
        from services.fx_engine.models import FXQuote

        quote = FXQuote(
            quote_id="qte_exp",
            currency_pair="GBP/EUR",
            sell_amount=Decimal("1000"),
            sell_currency="GBP",
            buy_amount=Decimal("1160"),
            buy_currency="EUR",
            rate=Decimal("1.16"),
            spread=Decimal("0.005"),
            created_at=(datetime.now(UTC) - timedelta(seconds=60)).isoformat(),
            expires_at=(datetime.now(UTC) - timedelta(seconds=30)).isoformat(),
        )
        store.save(quote)
        ex = FXExecutor(quote_store=store, execution_store=InMemoryExecutionStore())
        result = ex.execute("qte_exp", "user")
        assert isinstance(result, FXExecution)
        assert result.status == ExecutionStatus.EXPIRED

    def test_nonexistent_quote_returns_rejected(self, executor):
        result = executor.execute("nonexistent_quote", "user")
        assert isinstance(result, FXExecution)
        assert result.status == ExecutionStatus.REJECTED


class TestReject:
    def test_reject_returns_hitl_proposal(self, executor):
        proposal = executor.reject("qte_001", "Invalid", "user")
        assert isinstance(proposal, HITLProposal)

    def test_reject_always_l4(self, executor):
        proposal = executor.reject("qte_001", "reason", "user")
        assert proposal.autonomy_level == "L4"

    def test_reject_requires_treasury_ops(self, executor):
        proposal = executor.reject("qte_001", "reason", "user")
        assert proposal.requires_approval_from == "TREASURY_OPS"

    def test_reject_action_name(self, executor):
        proposal = executor.reject("qte_001", "reason", "user")
        assert proposal.action == "REJECT_QUOTE"


class TestGetExecution:
    def test_get_execution_by_id(self, executor, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("500"), "GBP")
        execution = executor.execute(quote.quote_id, "user")
        if isinstance(execution, FXExecution):
            fetched = executor.get_execution(execution.execution_id)
            assert fetched is not None
            assert fetched.execution_id == execution.execution_id

    def test_get_nonexistent_execution_none(self, executor):
        assert executor.get_execution("nonexistent") is None

    def test_get_executions_by_quote(self, executor, quoter):
        quote = quoter.create_quote("GBP/EUR", Decimal("500"), "GBP")
        executor.execute(quote.quote_id, "user")
        executions = executor.get_executions_by_quote(quote.quote_id)
        assert len(executions) >= 1
