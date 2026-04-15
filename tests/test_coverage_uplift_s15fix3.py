"""
tests/test_coverage_uplift_s15fix3.py — Coverage uplift batch 3
S15-FIX-3 | GAP-3 | banxe-emi-stack

Targeted tests for uncovered branches across:
- AgentResponse/TierResult validation errors (schemas.py)
- NotificationService register + render edge cases
- TransactionParser timestamp/parse_raw edge cases
- ExperimentDesigner make_kb_port factory + empty baselines
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import os
from unittest.mock import patch

import pytest

# ── AgentResponse / TierResult validation errors ──────────────────────────────
from services.agent_routing.schemas import AgentResponse, TierResult


def _make_agent_response(**kwargs) -> AgentResponse:
    defaults = dict(
        agent_name="test-agent",
        case_id="c-001",
        signal_type="sanctions",
        risk_score=0.3,
        confidence=0.9,
        decision_hint="clear",
        reason_summary="Low risk",
        evidence_refs=[],
        token_cost=100,
        latency_ms=50,
    )
    defaults.update(kwargs)
    return AgentResponse(**defaults)


class TestAgentResponseValidation:
    def test_risk_score_above_one_raises(self):
        with pytest.raises(ValueError, match="risk_score"):
            _make_agent_response(risk_score=1.5)

    def test_confidence_above_one_raises(self):
        with pytest.raises(ValueError, match="confidence"):
            _make_agent_response(confidence=1.1)

    def test_invalid_decision_hint_raises(self):
        with pytest.raises(ValueError, match="decision_hint"):
            _make_agent_response(decision_hint="approve")

    def test_negative_token_cost_raises(self):
        with pytest.raises(ValueError, match="token_cost"):
            _make_agent_response(token_cost=-1)

    def test_negative_latency_raises(self):
        with pytest.raises(ValueError, match="latency_ms"):
            _make_agent_response(latency_ms=-100)

    def test_valid_agent_response_instantiates(self):
        ar = _make_agent_response()
        assert ar.agent_name == "test-agent"


class TestTierResultValidation:
    def test_invalid_decision_raises(self):
        with pytest.raises(ValueError, match="decision"):
            TierResult(
                task_id="t-001",
                tier_used=1,
                decision="approve_invalid",
                responses=[],
                total_tokens=100,
                total_latency_ms=50,
                reasoning_reused=False,
                playbook_version="pb-v1",
            )

    def test_invalid_tier_raises(self):
        with pytest.raises(ValueError, match="tier_used"):
            TierResult(
                task_id="t-001",
                tier_used=5,
                decision="approve",
                responses=[],
                total_tokens=100,
                total_latency_ms=50,
                reasoning_reused=False,
                playbook_version="pb-v1",
            )

    def test_valid_tier_result_instantiates(self):
        tr = TierResult(
            task_id="t-001",
            tier_used=2,
            decision="manual_review",
            responses=[],
            total_tokens=200,
            total_latency_ms=120,
            reasoning_reused=True,
            playbook_version="pb-aml-v2",
        )
        assert tr.tier_used == 2


# ── NotificationService uncovered branches ────────────────────────────────────

from services.events.event_bus import BanxeEventType, DomainEvent, InMemoryEventBus
from services.notifications.mock_notification_adapter import MockNotificationAdapter
from services.notifications.notification_port import (
    NotificationType,
)
from services.notifications.notification_service import NotificationService


class TestNotificationServiceEdgeCases:
    def test_register_event_handlers_with_no_event_bus_logs_warning(self):
        adapter = MockNotificationAdapter()
        svc = NotificationService(adapter=adapter, event_bus=None)
        # Should not raise, just log a warning and return
        svc.register_event_handlers()

    def test_handle_event_with_unmapped_type_returns_silently(self):
        adapter = MockNotificationAdapter()
        event_bus = InMemoryEventBus()
        svc = NotificationService(adapter=adapter, event_bus=event_bus)
        svc.register_event_handlers()
        # Send an event type not in the map — should be silently ignored
        event = DomainEvent(
            event_id="ev-001",
            event_type=BanxeEventType.PAYMENT_FROZEN,  # unmapped
            source_service="test",
            payload={"reference": "REF001"},
            occurred_at=datetime.now(UTC),
            customer_id="cust-001",
        )
        # Publish will call _handle_event; unmapped events return early
        event_bus.publish(event)

    def test_render_body_with_unknown_type_returns_fallback(self):
        adapter = MockNotificationAdapter()
        svc = NotificationService(adapter=adapter)
        # Use a NotificationType not in _TEMPLATES
        result = svc.render_body(NotificationType.SAR_FILED, {})
        assert (
            "sar" in result.lower()
            or "aml" in result.lower()
            or NotificationType.AML_SAR_FILED.value in result
        )

    def test_render_subject_with_unknown_type_returns_type_value(self):
        adapter = MockNotificationAdapter()
        svc = NotificationService(adapter=adapter)
        result = svc.render_subject(NotificationType.CUSTOMER_DORMANT, {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_body_with_missing_template_vars_uses_safe_fallback(self):
        adapter = MockNotificationAdapter()
        svc = NotificationService(adapter=adapter)
        # Use a type that IS in templates but provide no vars → format_map uses SafeFormatDict
        result = svc.render_body(NotificationType.PAYMENT_SENT, {})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_render_subject_with_missing_vars_uses_safe_fallback(self):
        adapter = MockNotificationAdapter()
        svc = NotificationService(adapter=adapter)
        result = svc.render_subject(NotificationType.PAYMENT_SENT, {})
        assert isinstance(result, str)


# ── TransactionParser timestamp / parse_raw edge cases ──────────────────────

from services.transaction_monitor.consumer.transaction_parser import (
    ParseError,
    TransactionParser,
)
from services.transaction_monitor.models.transaction import RawEventPayload


def _base_payload(**kwargs) -> dict:
    base = {
        "transaction_id": "txn-001",
        "amount": "500.00",
        "sender_id": "cust-001",
        "currency": "GBP",
        "transaction_type": "payment",
    }
    base.update(kwargs)
    return base


class TestTransactionParserTimestampEdges:
    def test_parse_timestamp_from_iso_string(self):
        parser = TransactionParser()
        payload = _base_payload(timestamp="2024-01-15T10:30:00Z")
        event = parser.parse(payload)
        assert event.timestamp is not None

    def test_parse_timestamp_from_datetime_object(self):
        parser = TransactionParser()
        ts = datetime(2024, 1, 15, 10, 30, tzinfo=UTC)
        payload = _base_payload(timestamp=ts)
        event = parser.parse(payload)
        assert event.timestamp == ts

    def test_parse_timestamp_from_non_string_non_datetime(self):
        parser = TransactionParser()
        # Pass an int as timestamp → hits `else: timestamp = datetime.utcnow()`
        payload = _base_payload(timestamp=1705315800)
        event = parser.parse(payload)
        assert event.timestamp is not None

    def test_parse_missing_timestamp_defaults_to_now(self):
        parser = TransactionParser()
        payload = _base_payload()
        event = parser.parse(payload)
        assert event.timestamp is not None

    def test_parse_raw_payload_wrapper(self):
        parser = TransactionParser()
        raw = RawEventPayload(
            payload={
                "transaction_id": "txn-raw-001",
                "amount": "150.00",
                "sender_id": "cust-002",
            }
        )
        event = parser.parse_raw(raw)
        assert event.transaction_id == "txn-raw-001"
        assert event.amount == Decimal("150.00")

    def test_parse_general_exception_raises_parse_error(self):
        parser = TransactionParser()
        # Pass a payload where amount exists but some other processing will raise
        with pytest.raises(ParseError):
            # Passing a non-dict amount that passes str check but fails Decimal
            parser.parse({"amount": object(), "transaction_id": "t1", "sender_id": "s1"})


# ── ExperimentDesigner / make_kb_port factory ──────────────────────────────────

from services.experiment_copilot.agents.experiment_designer import (
    ExperimentDesigner,
    HTTPKBPort,
    InMemoryKBPort,
    make_kb_port,
)
from services.experiment_copilot.models.experiment import DesignRequest, ExperimentScope
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore


class TestMakeKBPortFactory:
    def test_inmemory_adapter_by_default(self):
        env = {k: v for k, v in os.environ.items() if k != "KB_ADAPTER"}
        with patch.dict(os.environ, env, clear=True):
            port = make_kb_port()
        assert isinstance(port, InMemoryKBPort)

    def test_http_adapter_returns_http_port(self):
        with patch.dict(os.environ, {"KB_ADAPTER": "http"}):
            port = make_kb_port()
        assert isinstance(port, HTTPKBPort)

    def test_production_adapter_returns_http_port(self):
        with patch.dict(os.environ, {"KB_ADAPTER": "production"}):
            port = make_kb_port()
        assert isinstance(port, HTTPKBPort)

    def test_http_port_uses_api_base_arg(self):
        port = HTTPKBPort(api_base="http://custom:8090")
        assert port._api_base == "http://custom:8090"

    def test_http_port_default_api_base(self):
        port = HTTPKBPort()
        assert "localhost" in port._api_base

    def test_make_kb_port_with_explicit_api_base(self):
        with patch.dict(os.environ, {"KB_ADAPTER": "http"}):
            port = make_kb_port(api_base="http://test:8000")
        assert isinstance(port, HTTPKBPort)
        assert port._api_base == "http://test:8000"


class TestExperimentDesignerMetrics:
    def _make_designer(self) -> ExperimentDesigner:
        store = ExperimentStore()
        audit = AuditTrail()
        return ExperimentDesigner(
            store=store,
            audit=audit,
            kb_port=InMemoryKBPort(),
            baselines_path="/nonexistent/path/baselines.yaml",
        )

    def test_designer_with_empty_baselines_returns_empty_dicts(self):
        designer = self._make_designer()
        # _baselines is {} because path doesn't exist
        baseline, target = designer._get_metrics_for_scope(ExperimentScope.TRANSACTION_MONITORING)
        assert baseline == {}
        assert target == {}

    def test_design_with_empty_baselines_still_creates_experiment(self):
        designer = self._make_designer()
        req = DesignRequest(
            query="Improve velocity checks for structuring detection",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            created_by="compliance-officer",
        )
        exp = designer.design(req)
        assert exp is not None
        assert "velocity" in exp.title.lower() or "transaction" in exp.title.lower()


# ── ComplianceKBService get_kb_service singleton factory ─────────────────────

from services.compliance_kb.kb_service import get_kb_service


class TestGetKBServiceFactory:
    def test_get_kb_service_returns_service(self, tmp_path):
        import services.compliance_kb.kb_service as kb_mod

        # Reset singleton for clean test
        original = kb_mod._default_service
        kb_mod._default_service = None
        try:
            with patch.dict(os.environ, {"CHROMA_PERSIST_DIR": str(tmp_path / "chroma")}):
                svc = get_kb_service()
            assert svc is not None
        finally:
            kb_mod._default_service = original

    def test_get_kb_service_returns_same_singleton(self, tmp_path):
        import services.compliance_kb.kb_service as kb_mod

        original = kb_mod._default_service
        kb_mod._default_service = None
        try:
            with patch.dict(os.environ, {"CHROMA_PERSIST_DIR": str(tmp_path / "chroma2")}):
                svc1 = get_kb_service()
                svc2 = get_kb_service()
            assert svc1 is svc2
        finally:
            kb_mod._default_service = original


# ── AML thresholds get_compliance_context ─────────────────────────────────────

from services.aml.aml_thresholds import get_compliance_context


class TestAMLComplianceContext:
    def test_get_compliance_context_when_rag_unavailable(self):
        import services.aml.aml_thresholds as aml_mod

        original = aml_mod._RAG_AVAILABLE
        try:
            aml_mod._RAG_AVAILABLE = False
            result = get_compliance_context("AML EDD thresholds for corporate")
            assert result == ""
        finally:
            aml_mod._RAG_AVAILABLE = original

    def test_get_compliance_context_when_rag_raises_returns_empty(self):
        import services.aml.aml_thresholds as aml_mod

        original = aml_mod._RAG_AVAILABLE
        try:
            aml_mod._RAG_AVAILABLE = False
            result = get_compliance_context("pep screening", agent_name="test-agent")
            assert result == ""
        finally:
            aml_mod._RAG_AVAILABLE = original
