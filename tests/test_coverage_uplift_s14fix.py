"""
tests/test_coverage_uplift_s14fix.py — S14-FIX-1 targeted coverage uplift
S14-FIX-1 | banxe-emi-stack

Targets modules with < 85% coverage that were not addressed in Sprint 14:

  1. services/aml/aml_thresholds.py       86% → ~100%
  2. services/transaction_monitor/scoring/rule_engine.py  58% → ~95%
  3. services/transaction_monitor/scoring/velocity_tracker.py  57% → ~80%
  4. services/transaction_monitor/scoring/risk_scorer.py  78% → ~95%
  5. services/recon/bankstatement_parser.py  73% → ~95%
  6. services/experiment_copilot/agents/experiment_steward.py  82% → ~95%

No external dependencies required — uses InMemory adapters and stdlib mocks.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

# ═══════════════════════════════════════════════════════════════════════════════
# Section 1 — AML Thresholds
# ═══════════════════════════════════════════════════════════════════════════════


class TestAMLThresholds:
    from services.aml.aml_thresholds import (  # noqa: PLC0415
        COMPANY_THRESHOLDS,
        INDIVIDUAL_THRESHOLDS,
        get_thresholds,
    )

    def test_get_thresholds_individual(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS, get_thresholds

        assert get_thresholds("INDIVIDUAL") is INDIVIDUAL_THRESHOLDS

    def test_get_thresholds_company(self):
        from services.aml.aml_thresholds import COMPANY_THRESHOLDS, get_thresholds

        assert get_thresholds("COMPANY") is COMPANY_THRESHOLDS

    def test_get_thresholds_unknown_defaults_to_individual(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS, get_thresholds

        assert get_thresholds("UNKNOWN_ENTITY") is INDIVIDUAL_THRESHOLDS

    def test_requires_edd_individual_above_threshold(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("10000")) is True
        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("15000")) is True

    def test_requires_edd_individual_below_threshold(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("9999.99")) is False

    def test_requires_edd_pep_uses_lower_threshold(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        # PEP threshold = 10000 * 0.5 = 5000
        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("5000"), is_pep=True) is True
        assert INDIVIDUAL_THRESHOLDS.requires_edd(Decimal("4999"), is_pep=True) is False

    def test_edd_for_pep_formula(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        pep_threshold = INDIVIDUAL_THRESHOLDS.edd_for_pep()
        assert pep_threshold == Decimal("5000.00")

    def test_requires_sar_consideration_above(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.requires_sar_consideration(Decimal("50000")) is True
        assert INDIVIDUAL_THRESHOLDS.requires_sar_consideration(Decimal("60000")) is True

    def test_requires_sar_consideration_below(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.requires_sar_consideration(Decimal("49999")) is False

    def test_is_velocity_daily_breach_by_amount(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("25000"), 3) is True

    def test_is_velocity_daily_breach_by_count(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("1000"), 10) is True

    def test_is_velocity_daily_no_breach(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_velocity_daily_breach(Decimal("100"), 1) is False

    def test_is_velocity_monthly_breach(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_velocity_monthly_breach(Decimal("100000"), 10) is True

    def test_is_structuring_signal(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        # 3+ txs AND total >= 9000 → structuring signal (POCA 2002)
        assert INDIVIDUAL_THRESHOLDS.is_structuring_signal(3, Decimal("9000")) is True

    def test_is_structuring_signal_insufficient_count(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_structuring_signal(2, Decimal("9000")) is False

    def test_is_structuring_signal_insufficient_amount(self):
        from services.aml.aml_thresholds import INDIVIDUAL_THRESHOLDS

        assert INDIVIDUAL_THRESHOLDS.is_structuring_signal(3, Decimal("8999")) is False

    def test_company_thresholds_higher_than_individual(self):
        from services.aml.aml_thresholds import COMPANY_THRESHOLDS, INDIVIDUAL_THRESHOLDS

        assert COMPANY_THRESHOLDS.edd_trigger > INDIVIDUAL_THRESHOLDS.edd_trigger
        assert COMPANY_THRESHOLDS.sar_auto_single > INDIVIDUAL_THRESHOLDS.sar_auto_single


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2 — Rule Engine
# ═══════════════════════════════════════════════════════════════════════════════


def _make_tx_event(**kwargs):
    """Helper: create a minimal TransactionEvent."""
    from services.transaction_monitor.models.transaction import TransactionEvent

    defaults = {
        "transaction_id": "tx-test-001",
        "amount": Decimal("100"),
        "sender_id": "cust-001",
        "sender_jurisdiction": "GB",
    }
    defaults.update(kwargs)
    return TransactionEvent(**defaults)


class TestRuleEngine:
    def test_jurisdiction_hard_block_returns_critical_score(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        engine = RuleEngine()
        event = _make_tx_event(sender_jurisdiction="RU")
        features = {"jurisdiction_risk": 1.0}
        score, factors = engine.evaluate(event, features)

        assert score == 1.0
        assert len(factors) == 1
        assert factors[0].name == "jurisdiction_hard_block"

    def test_jurisdiction_hard_block_sender_name_in_explanation(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        engine = RuleEngine()
        event = _make_tx_event(sender_jurisdiction="KP")
        score, factors = engine.evaluate(event, {"jurisdiction_risk": 1.0})
        assert "KP" in factors[0].explanation

    def test_jube_exception_uses_fallback_score(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        class FailingJubePort:
            def evaluate(self, tx_data):
                raise ConnectionError("Jube unreachable")

        engine = RuleEngine(jube_port=FailingJubePort())
        event = _make_tx_event()
        features = {"velocity_24h": 0.8, "jurisdiction_risk": 0.0}
        score, factors = engine.evaluate(event, features)

        # Fallback: no factors returned
        assert isinstance(score, float)
        assert len(factors) == 0

    def test_fallback_score_jurisdiction_adds_0_4(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        score = RuleEngine._fallback_score({"jurisdiction_risk": 0.6})
        assert abs(score - 0.4) < 1e-9

    def test_fallback_score_velocity_adds_0_3(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        score = RuleEngine._fallback_score({"velocity_24h": 0.8})
        assert abs(score - 0.3) < 1e-9

    def test_fallback_score_all_zero(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        score = RuleEngine._fallback_score({})
        assert score == 0.0

    def test_fallback_score_capped_at_1(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        score = RuleEngine._fallback_score(
            {
                "jurisdiction_risk": 0.6,
                "velocity_24h": 0.9,
                "amount_deviation": 0.9,
                "round_amount": 0.9,
            }
        )
        assert score <= 1.0

    def test_normal_jube_evaluation_returns_score_and_factors(self):
        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        engine = RuleEngine()  # uses InMemoryJubePort with score=0.35
        event = _make_tx_event()
        features = {"jurisdiction_risk": 0.0}
        score, factors = engine.evaluate(event, features)

        assert score == pytest.approx(0.35)
        assert len(factors) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3 — Risk Scorer + IsolationForestModel
# ═══════════════════════════════════════════════════════════════════════════════


class TestRiskScorer:
    def test_isolation_forest_model_missing_file_falls_back(self):
        from services.transaction_monitor.scoring.risk_scorer import IsolationForestModel

        model = IsolationForestModel(model_path="/tmp/nonexistent_model_xyz.pkl")
        # Should not raise — falls back to InMemoryMLModel
        score = model.score({"velocity_24h": 0.5, "jurisdiction_risk": 0.1})
        assert 0.0 <= score <= 1.0

    def test_risk_scorer_scores_normal_transaction(self):
        from services.transaction_monitor.scoring.risk_scorer import RiskScorer

        scorer = RiskScorer()
        event = _make_tx_event(amount=Decimal("500"))
        result = scorer.score(event)

        assert 0.0 <= result.score <= 1.0
        assert result.classification in {"low", "medium", "high", "critical"}
        assert len(result.factors) >= 2

    def test_risk_scorer_hard_blocked_jurisdiction_returns_critical(self):
        from services.transaction_monitor.scoring.risk_scorer import RiskScorer

        scorer = RiskScorer()
        event = _make_tx_event(sender_jurisdiction="IR")  # Iran — hard block I-02
        result = scorer.score(event)

        assert result.score == 1.0
        assert result.classification == "critical"

    def test_risk_scorer_records_velocity_after_score(self):
        from services.transaction_monitor.scoring.risk_scorer import RiskScorer
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        scorer = RiskScorer(velocity_tracker=tracker)
        event = _make_tx_event(sender_id="cust-vel-001")
        scorer.score(event)

        # Velocity should be recorded
        assert tracker.get_count("cust-vel-001", "24h") == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4 — InMemoryVelocityTracker
# ═══════════════════════════════════════════════════════════════════════════════


class TestInMemoryVelocityTracker:
    def test_record_increments_all_windows(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_id="cust-v", amount=Decimal("1000"))
        tracker.record(event)

        assert tracker.get_count("cust-v", "1h") == 1
        assert tracker.get_count("cust-v", "24h") == 1
        assert tracker.get_count("cust-v", "7d") == 1

    def test_get_cumulative_amount_after_record(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_id="cust-amt", amount=Decimal("2500"))
        tracker.record(event)
        tracker.record(event)

        assert tracker.get_cumulative_amount("cust-amt", "24h") == Decimal("5000")

    def test_is_hard_blocked_sanctioned_sender(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_jurisdiction="BY")  # Belarus — blocked
        assert tracker.is_hard_blocked(event) is True

    def test_is_hard_blocked_sanctioned_receiver(self):
        from services.transaction_monitor.models.transaction import TransactionEvent
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = TransactionEvent(
            transaction_id="tx-recv-block",
            amount=Decimal("100"),
            sender_id="cust-gb",
            sender_jurisdiction="GB",
            receiver_jurisdiction="KP",  # North Korea — blocked
        )
        assert tracker.is_hard_blocked(event) is True

    def test_is_not_hard_blocked_gb(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_jurisdiction="GB")
        assert tracker.is_hard_blocked(event) is False

    def test_requires_edd_above_threshold(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_id="cust-edd", amount=Decimal("10001"))
        tracker.record(event)
        assert tracker.requires_edd("cust-edd") is True

    def test_requires_edd_below_threshold(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        event = _make_tx_event(sender_id="cust-noedd", amount=Decimal("100"))
        tracker.record(event)
        assert tracker.requires_edd("cust-noedd") is False

    def test_get_count_no_events_returns_zero(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        assert tracker.get_count("nonexistent-cust", "24h") == 0

    def test_get_cumulative_amount_no_events_returns_zero(self):
        from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker

        tracker = InMemoryVelocityTracker()
        assert tracker.get_cumulative_amount("no-cust", "24h") == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 5 — BankStatement Parser
# ═══════════════════════════════════════════════════════════════════════════════


class TestBankStatementParser:
    def test_parse_camt053_without_library_returns_empty(self):
        """When bankstatementparser is not installed, returns []."""
        from services.recon.bankstatement_parser import parse_camt053

        result = parse_camt053(Path("/tmp/fake_camt053.xml"))
        assert result == []

    def test_parse_mt940_without_library_returns_empty(self):
        """When mt940 is not installed, returns []."""
        from services.recon.bankstatement_parser import parse_mt940

        result = parse_mt940(Path("/tmp/fake_mt940.sta"))
        assert result == []

    def test_validate_statement_balance_valid(self):
        from services.recon.bankstatement_parser import validate_statement_balance

        txns = [Decimal("100"), Decimal("200"), Decimal("-50")]
        opening = Decimal("1000")
        closing = Decimal("1250")
        # Should not raise
        validate_statement_balance(txns, opening, closing)

    def test_validate_statement_balance_invalid_raises(self):
        from services.recon.bankstatement_parser import validate_statement_balance

        txns = [Decimal("100")]
        opening = Decimal("1000")
        closing = Decimal("1200")  # 100 != 200
        with pytest.raises(ValueError, match="balance validation failed"):
            validate_statement_balance(txns, opening, closing)

    def test_validate_statement_balance_empty_txns_valid(self):
        from services.recon.bankstatement_parser import validate_statement_balance

        # No transactions — opening == closing
        validate_statement_balance([], Decimal("1000"), Decimal("1000"))

    def test_decimal_from_amount_already_decimal(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        d = Decimal("123.45")
        assert _decimal_from_amount(d) == d
        assert isinstance(_decimal_from_amount(d), Decimal)

    def test_decimal_from_amount_from_string(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        assert _decimal_from_amount("456.78") == Decimal("456.78")

    def test_decimal_from_amount_from_int(self):
        from services.recon.bankstatement_parser import _decimal_from_amount

        assert _decimal_from_amount(100) == Decimal("100")

    def test_extract_date_from_object_with_date_method(self):
        from services.recon.bankstatement_parser import _extract_date

        class FakeStmt:
            closing_date = datetime(2026, 4, 13, 10, 30)

        result = _extract_date(FakeStmt())
        assert result == date(2026, 4, 13)

    def test_extract_date_none_returns_today(self):
        from services.recon.bankstatement_parser import _extract_date

        class FakeStmt:
            closing_date = None
            creation_date = None

        result = _extract_date(FakeStmt())
        assert result == date.today()

    def test_extract_date_from_date_object(self):
        from services.recon.bankstatement_parser import _extract_date

        d = date(2026, 1, 15)

        class FakeStmt:
            closing_date = d

        result = _extract_date(FakeStmt())
        assert result == d


# ═══════════════════════════════════════════════════════════════════════════════
# Section 6 — Experiment Steward
# ═══════════════════════════════════════════════════════════════════════════════


def _make_valid_experiment(exp_id: str = "exp-steward-001", *, tmp_path: Path):
    """Create a valid DRAFT ComplianceExperiment."""
    from services.experiment_copilot.models.experiment import (
        ComplianceExperiment,
        ExperimentScope,
        ExperimentStatus,
    )

    return ComplianceExperiment(
        id=exp_id,
        title="Velocity threshold P2P test",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=ExperimentStatus.DRAFT,
        hypothesis="Reducing the P2P velocity threshold from 15 to 10 transactions per 24h will reduce false negatives by 15%",
        kb_citations=["EBA GL/2021/02 §4.2"],
        metrics_baseline={"false_negative_rate": "12%"},
        metrics_target={"false_negative_rate": "8%"},
    )


class TestExperimentSteward:
    def test_approve_valid_experiment_moves_to_active(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.models.experiment import ApproveRequest, ExperimentStatus
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        exp = _make_valid_experiment("exp-approve-01", tmp_path=tmp_path)
        store.save(exp)

        result = steward.approve("exp-approve-01", ApproveRequest(steward_notes="LGTM"))
        assert result.status == ExperimentStatus.ACTIVE
        assert result.steward_notes == "LGTM"

    def test_approve_invalid_experiment_raises_validation_error(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import (
            ExperimentSteward,
            ValidationError,
        )
        from services.experiment_copilot.models.experiment import (
            ApproveRequest,
            ComplianceExperiment,
            ExperimentScope,
        )
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        # Too-short hypothesis
        exp = ComplianceExperiment(
            id="exp-invalid-01",
            title="Bad exp",
            scope=ExperimentScope.KYC_ONBOARDING,
            hypothesis="Too short",  # < 20 chars
            kb_citations=[],
            metrics_baseline={},
            metrics_target={},
        )
        store.save(exp)

        with pytest.raises(ValidationError, match="failed validation"):
            steward.approve("exp-invalid-01", ApproveRequest())

    def test_reject_non_draft_raises_value_error(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.models.experiment import (
            ApproveRequest,
            RejectRequest,
        )
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        exp = _make_valid_experiment("exp-reject-01", tmp_path=tmp_path)
        store.save(exp)
        # First approve it so it's ACTIVE
        steward.approve("exp-reject-01", ApproveRequest(steward_notes="ok"))

        with pytest.raises(ValueError, match="DRAFT"):
            steward.reject("exp-reject-01", RejectRequest(reason="Not draft — should fail here"))

    def test_finish_non_active_raises_value_error(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        exp = _make_valid_experiment("exp-finish-draft-01", tmp_path=tmp_path)
        store.save(exp)

        with pytest.raises(ValueError, match="ACTIVE"):
            steward.finish("exp-finish-draft-01", notes="cannot finish DRAFT")

    def test_approve_not_found_raises_value_error(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.models.experiment import ApproveRequest
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        with pytest.raises(ValueError, match="not found"):
            steward.approve("nonexistent-exp", ApproveRequest())

    def test_generate_weekly_report_returns_markdown(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        report = steward.generate_weekly_report()
        assert "# Compliance Experiment Weekly Report" in report
        assert "Total experiments" in report

    def test_validate_returns_errors_for_invalid_experiment(self, tmp_path):
        from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
        from services.experiment_copilot.models.experiment import (
            ComplianceExperiment,
            ExperimentScope,
        )
        from services.experiment_copilot.store.audit_trail import AuditTrail
        from services.experiment_copilot.store.experiment_store import ExperimentStore

        store = ExperimentStore(experiments_dir=str(tmp_path))
        audit = AuditTrail(log_path=tmp_path / "audit.jsonl")
        steward = ExperimentSteward(store=store, audit=audit)

        exp = ComplianceExperiment(
            id="exp-validate-01",
            title="T",
            scope=ExperimentScope.SAR_FILING,
            hypothesis="short",
            kb_citations=[],
            metrics_baseline={},
            metrics_target={},
        )
        errors = steward.validate(exp)
        assert len(errors) > 0
        assert any("Hypothesis" in e for e in errors)
        assert any("KB citation" in e for e in errors)
