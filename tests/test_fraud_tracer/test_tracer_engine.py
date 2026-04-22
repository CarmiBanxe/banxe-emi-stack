"""Tests for Fraud Transaction Tracer (IL-TRC-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.fraud_tracer.tracer_engine import (
    BLOCKED_JURISDICTIONS,
    EDD_THRESHOLD,
    TracerEngine,
)
from services.fraud_tracer.tracer_models import TracerConfig, TraceRequest
from services.fraud_tracer.velocity_checker import InMemoryVelocityPort, VelocityChecker


def _make_request(
    amount: str = "100.00",
    country: str = "GB",
    counterparty: str = "GB",
    customer_id: str = "CUST001",
    tx_id: str = "TX001",
) -> TraceRequest:
    return TraceRequest(
        transaction_id=tx_id,
        customer_id=customer_id,
        amount=amount,
        currency="GBP",
        country=country,
        counterparty_country=counterparty,
    )


class TestTracerEngineBasic:
    def test_trace_clear_small_amount(self):
        engine = TracerEngine()
        req = _make_request(amount="100.00")
        result = engine.trace(req)
        assert result.status == "CLEAR"

    def test_score_is_string(self):
        """I-01: score stored as string (Decimal)."""
        engine = TracerEngine()
        req = _make_request(amount="100.00")
        result = engine.trace(req)
        assert isinstance(result.score, str)
        Decimal(result.score)

    def test_score_not_float(self):
        engine = TracerEngine()
        req = _make_request(amount="100.00")
        result = engine.trace(req)
        assert not isinstance(result.score, float)

    def test_latency_ms_is_int(self):
        engine = TracerEngine()
        req = _make_request(amount="100.00")
        result = engine.trace(req)
        assert isinstance(result.latency_ms, int)

    def test_latency_under_100ms(self):
        """Target p99 < 100ms."""
        engine = TracerEngine()
        req = _make_request(amount="100.00")
        result = engine.trace(req)
        assert result.latency_ms < 100

    def test_blocked_jurisdiction_ru_score_1(self):
        """I-02: RU jurisdiction -> score 1.0, BLOCK."""
        engine = TracerEngine()
        req = _make_request(country="RU")
        result = engine.trace(req)
        assert result.status == "BLOCK"
        assert Decimal(result.score) == Decimal("1.0")
        assert "BLOCKED_JURISDICTION" in result.flags

    def test_blocked_jurisdiction_ir(self):
        engine = TracerEngine()
        req = _make_request(country="IR")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_jurisdiction_kp(self):
        engine = TracerEngine()
        req = _make_request(country="KP")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_jurisdiction_by(self):
        engine = TracerEngine()
        req = _make_request(country="BY")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_jurisdiction_cu(self):
        engine = TracerEngine()
        req = _make_request(country="CU")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_jurisdiction_mm(self):
        engine = TracerEngine()
        req = _make_request(country="MM")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_jurisdiction_sy(self):
        engine = TracerEngine()
        req = _make_request(country="SY")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_blocked_counterparty_ru(self):
        engine = TracerEngine()
        req = _make_request(country="GB", counterparty="RU")
        result = engine.trace(req)
        assert result.status == "BLOCK"

    def test_allowed_jurisdiction_gb_clear(self):
        engine = TracerEngine()
        req = _make_request(country="GB")
        result = engine.trace(req)
        assert "BLOCKED_JURISDICTION" not in result.flags

    def test_edd_threshold_flag(self):
        """I-04: amount >= £10k flags EDD_THRESHOLD."""
        engine = TracerEngine()
        req = _make_request(amount="10000.00")
        result = engine.trace(req)
        assert "EDD_THRESHOLD" in result.flags

    def test_edd_threshold_boundary_below(self):
        engine = TracerEngine()
        req = _make_request(amount="9999.99")
        result = engine.trace(req)
        assert "EDD_THRESHOLD" not in result.flags

    def test_edd_threshold_above(self):
        engine = TracerEngine()
        req = _make_request(amount="50000.00")
        result = engine.trace(req)
        assert "EDD_THRESHOLD" in result.flags

    def test_edd_threshold_decimal(self):
        assert isinstance(EDD_THRESHOLD, Decimal)
        assert Decimal("10000.00") == EDD_THRESHOLD

    def test_trace_log_append_only(self):
        """I-24: trace_log grows with each trace call."""
        engine = TracerEngine()
        req1 = _make_request(tx_id="TX001")
        req2 = _make_request(tx_id="TX002")
        engine.trace(req1)
        engine.trace(req2)
        assert len(engine.trace_log) == 2

    def test_trace_log_has_timestamp(self):
        engine = TracerEngine()
        req = _make_request()
        engine.trace(req)
        assert "traced_at" in engine.trace_log[0]

    def test_bt009_ml_model_raises_not_implemented(self):
        """BT-009: ML model scoring is a stub."""
        engine = TracerEngine()
        with pytest.raises(NotImplementedError, match="BT-009"):
            engine.ml_model_score({})

    def test_blocked_jurisdictions_set(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "IR" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS

    def test_edd_threshold_sets_score_05(self):
        """£10k alone -> score=0.5 (below review threshold of 0.6 -> CLEAR)."""
        engine = TracerEngine()
        req = _make_request(amount="10000.00")
        result = engine.trace(req)
        assert Decimal(result.score) == Decimal("0.5")
        # score=0.5 < review_threshold=0.6 -> CLEAR
        assert result.status == "CLEAR"

    def test_trace_result_has_flags_list(self):
        engine = TracerEngine()
        req = _make_request()
        result = engine.trace(req)
        assert isinstance(result.flags, list)

    def test_trace_log_records_status(self):
        engine = TracerEngine()
        req = _make_request(country="RU")
        engine.trace(req)
        log = engine.trace_log
        assert log[0]["status"] == "BLOCK"

    def test_trace_log_initial_empty(self):
        engine = TracerEngine()
        assert len(engine.trace_log) == 0

    def test_velocity_and_edd_combined_block(self):
        """EDD(0.5) + velocity(0.4) = 0.9 >= 0.8 -> BLOCK."""
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        for _ in range(10):
            checker.record_transaction("CUST001", Decimal("100.00"))
        engine = TracerEngine(velocity_checker=checker)
        req = _make_request(amount="10000.00", customer_id="CUST001")
        result = engine.trace(req)
        assert result.status == "BLOCK"
        assert Decimal(result.score) == Decimal("0.9")


class TestVelocityChecker:
    def test_no_transactions_not_breached(self):
        checker = VelocityChecker(InMemoryVelocityPort())
        result = checker.check_velocity("CUST001")
        assert not result.breached
        assert result.tx_count == 0

    def test_record_and_check_count(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        for _ in range(5):
            checker.record_transaction("CUST001", Decimal("100.00"))
        result = checker.check_velocity("CUST001")
        assert result.tx_count == 5

    def test_velocity_breach_by_count(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        for _ in range(10):
            checker.record_transaction("CUST001", Decimal("100.00"))
        result = checker.check_velocity("CUST001")
        assert result.breached

    def test_velocity_breach_by_amount(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        checker.record_transaction("CUST001", Decimal("50000.00"))
        result = checker.check_velocity("CUST001")
        assert result.breached

    def test_total_amount_is_decimal_string(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        checker.record_transaction("CUST001", Decimal("500.00"))
        result = checker.check_velocity("CUST001")
        assert isinstance(result.total_amount, str)
        Decimal(result.total_amount)

    def test_velocity_not_breached_below_limits(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        for _ in range(3):
            checker.record_transaction("CUST001", Decimal("1000.00"))
        result = checker.check_velocity("CUST001")
        assert not result.breached

    def test_velocity_result_has_customer_id(self):
        checker = VelocityChecker(InMemoryVelocityPort())
        result = checker.check_velocity("CUST999")
        assert result.customer_id == "CUST999"

    def test_velocity_window_minutes_stored(self):
        checker = VelocityChecker(InMemoryVelocityPort())
        result = checker.check_velocity("CUST001", window_minutes=30)
        assert result.window_minutes == 30

    def test_velocity_total_amount_zero_when_no_tx(self):
        checker = VelocityChecker(InMemoryVelocityPort())
        result = checker.check_velocity("CUST001")
        assert Decimal(result.total_amount) == Decimal("0")

    def test_velocity_total_accumulates(self):
        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        checker.record_transaction("CUST001", Decimal("100.00"))
        checker.record_transaction("CUST001", Decimal("200.00"))
        result = checker.check_velocity("CUST001")
        assert Decimal(result.total_amount) == Decimal("300.00")


class TestFraudTracerAgent:
    def test_low_score_returns_trace_result(self):
        from services.fraud_tracer.tracer_agent import FraudTracerAgent
        from services.fraud_tracer.tracer_models import TraceResult

        agent = FraudTracerAgent()
        req = _make_request(amount="100.00")
        result = agent.trace_and_decide(req)
        assert isinstance(result, TraceResult)

    def test_blocked_jurisdiction_returns_hitl_proposal(self):
        from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="RU")
        result = agent.trace_and_decide(req)
        assert isinstance(result, FraudHITLProposal)

    def test_hitl_proposal_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="RU")
        result = agent.trace_and_decide(req)
        assert isinstance(result, FraudHITLProposal)
        assert result.approved is False

    def test_hitl_proposal_requires_fraud_analyst(self):
        from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="IR")
        result = agent.trace_and_decide(req)
        assert isinstance(result, FraudHITLProposal)
        assert result.requires_approval_from == "FRAUD_ANALYST"

    def test_proposals_appended(self):
        from services.fraud_tracer.tracer_agent import FraudTracerAgent

        agent = FraudTracerAgent()
        req1 = _make_request(country="RU", tx_id="TX001")
        req2 = _make_request(country="IR", tx_id="TX002")
        agent.trace_and_decide(req1)
        agent.trace_and_decide(req2)
        assert len(agent.proposals) == 2

    def test_edd_threshold_triggers_clear_not_block(self):
        """£10k alone sets score=0.5 -> CLEAR (below review=0.6, not BLOCK at 0.8)."""
        from services.fraud_tracer.tracer_agent import FraudTracerAgent
        from services.fraud_tracer.tracer_models import TraceResult

        agent = FraudTracerAgent()
        req = _make_request(amount="10000.00")
        result = agent.trace_and_decide(req)
        assert isinstance(result, TraceResult)
        # score=0.5 < review_threshold=0.6 -> CLEAR
        assert result.status == "CLEAR"

    def test_velocity_breach_alone_sets_clear(self):
        """velocity breach score=0.4 < review_threshold=0.6 -> CLEAR."""
        from services.fraud_tracer.tracer_agent import FraudTracerAgent
        from services.fraud_tracer.tracer_models import TraceResult

        port = InMemoryVelocityPort()
        checker = VelocityChecker(port)
        for _ in range(10):
            checker.record_transaction("CUST001", Decimal("100.00"))
        engine = TracerEngine(velocity_checker=checker)
        agent = FraudTracerAgent(engine)
        req = _make_request(amount="100.00", customer_id="CUST001")
        result = agent.trace_and_decide(req)
        assert isinstance(result, TraceResult)
        # score=0.4 < review=0.6 -> CLEAR
        assert result.status == "CLEAR"

    def test_tracer_config_defaults(self):
        config = TracerConfig()
        assert config.max_tx_count == 10
        assert Decimal(config.max_tx_amount) == Decimal("50000.00")
        assert not isinstance(config.max_tx_amount, float)

    def test_proposal_has_transaction_id(self):
        from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="RU", tx_id="TX_UNIQUE")
        result = agent.trace_and_decide(req)
        assert isinstance(result, FraudHITLProposal)
        assert result.transaction_id == "TX_UNIQUE"

    def test_proposal_score_is_string(self):
        from services.fraud_tracer.tracer_agent import FraudHITLProposal, FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="RU")
        result = agent.trace_and_decide(req)
        assert isinstance(result, FraudHITLProposal)
        assert isinstance(result.score, str)
        Decimal(result.score)

    def test_proposals_list_is_copy(self):
        from services.fraud_tracer.tracer_agent import FraudTracerAgent

        agent = FraudTracerAgent()
        req = _make_request(country="RU", tx_id="TX001")
        agent.trace_and_decide(req)
        props = agent.proposals
        props.clear()
        assert len(agent.proposals) == 1

    def test_fraud_hitl_threshold_is_decimal(self):
        from services.fraud_tracer.tracer_agent import FraudTracerAgent

        assert Decimal("0.8") == FraudTracerAgent.HITL_THRESHOLD
        assert isinstance(FraudTracerAgent.HITL_THRESHOLD, Decimal)

    def test_trace_log_contains_flags(self):
        engine = TracerEngine()
        req = _make_request(country="RU")
        engine.trace(req)
        log = engine.trace_log
        assert "BLOCKED_JURISDICTION" in log[0]["flags"]

    def test_trace_request_frozen(self):
        req = _make_request()
        with pytest.raises((TypeError, ValueError, AttributeError)):
            req.amount = "999.99"  # type: ignore[misc]

    def test_tracer_config_score_thresholds_decimal(self):
        config = TracerConfig()
        review = Decimal(config.score_threshold_review)
        block = Decimal(config.score_threshold_block)
        assert review < block
        assert review == Decimal("0.6")
        assert block == Decimal("0.8")

    def test_velocity_checker_default_config(self):
        checker = VelocityChecker()
        result = checker.check_velocity("CUST001")
        assert result.window_minutes == 60
        assert not result.breached

    def test_in_memory_velocity_port_separate_customers(self):
        port = InMemoryVelocityPort()
        port.record_tx("CUST001", Decimal("100.00"))
        port.record_tx("CUST002", Decimal("200.00"))
        count1 = port.get_tx_count("CUST001", 60)
        count2 = port.get_tx_count("CUST002", 60)
        total1 = port.get_tx_total("CUST001", 60)
        total2 = port.get_tx_total("CUST002", 60)
        assert count1 == 1
        assert count2 == 1
        assert total1 == Decimal("100.00")
        assert total2 == Decimal("200.00")


class TestMCPFraudTools:
    @pytest.mark.asyncio
    async def test_fraud_trace_tool_returns_json(self):
        import json
        from unittest.mock import AsyncMock, patch

        from banxe_mcp.server import fraud_trace

        with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {
                "transaction_id": "TX001",
                "score": "0.1",
                "status": "CLEAR",
            }
            result = await fraud_trace("TX001", "CUST001", "100.00")
            data = json.loads(result)
            assert "status" in data or "transaction_id" in data

    @pytest.mark.asyncio
    async def test_fraud_velocity_check_tool_returns_json(self):
        import json
        from unittest.mock import AsyncMock, patch

        from banxe_mcp.server import fraud_velocity_check

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "customer_id": "CUST001",
                "breached": False,
                "tx_count": 2,
            }
            result = await fraud_velocity_check("CUST001")
            data = json.loads(result)
            assert "customer_id" in data

    @pytest.mark.asyncio
    async def test_fraud_dashboard_tool_returns_json(self):
        import json
        from unittest.mock import AsyncMock, patch

        from banxe_mcp.server import fraud_dashboard

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "total_traced": 10,
                "blocked": 1,
                "clear": 8,
            }
            result = await fraud_dashboard()
            data = json.loads(result)
            assert "total_traced" in data
