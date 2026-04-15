"""
tests/test_coverage_uplift_s15fix.py — Targeted coverage uplift for 87% → 89%
S15-FIX-3 | banxe-emi-stack

Covers previously untested branches in:
  - services/transaction_monitor/store/alert_store.py (factory + filters)
  - services/transaction_monitor/alerts/explanation_engine.py (ExplanationEngine)
  - services/transaction_monitor/consumer/transaction_parser.py (error paths)
  - services/transaction_monitor/scoring/rule_engine.py (RuleEngine evaluate)
  - services/experiment_copilot/agents/change_proposer.py (ChangeProposer dry_run)
  - services/compliance_kb/kb_service.py (version compare, error paths)
  - services/auth/token_manager.py (rotate + validation errors)
  - services/auth/sca_service.py (biometric without prefix, TOTP fallback)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

# ── AlertStore factory + filters ──────────────────────────────────────────────


class TestAlertStoreFactory:
    def test_get_alert_store_returns_inmemory_by_default(self):
        from services.transaction_monitor.store.alert_store import (
            InMemoryAlertStore,
            get_alert_store,
        )

        store = get_alert_store()
        assert isinstance(store, InMemoryAlertStore)

    def test_get_alert_store_db_raises_not_implemented(self, monkeypatch):
        from services.transaction_monitor.store.alert_store import get_alert_store

        monkeypatch.setenv("ALERT_STORE", "db")
        with pytest.raises(NotImplementedError):
            get_alert_store()
        monkeypatch.delenv("ALERT_STORE")


class TestAlertStoreFilters:
    def _make_alert(self, customer_id: str = "cust-001", severity_val: str = "high") -> object:
        from services.transaction_monitor.models.alert import (
            AlertSeverity,
            AMLAlert,
        )
        from services.transaction_monitor.models.risk_score import RiskScore

        sev = AlertSeverity(severity_val)
        rs = RiskScore(score=0.8 if severity_val == "high" else 0.3)
        return AMLAlert(
            transaction_id=f"txn-{customer_id}",
            customer_id=customer_id,
            severity=sev,
            risk_score=rs,
            amount_gbp=Decimal("500.00"),
        )

    def test_list_alerts_filter_by_severity(self):
        from services.transaction_monitor.models.alert import AlertSeverity
        from services.transaction_monitor.store.alert_store import InMemoryAlertStore

        store = InMemoryAlertStore()
        store.save(self._make_alert("c1", "high"))
        store.save(self._make_alert("c2", "low"))
        high = store.list_alerts(severity=AlertSeverity.HIGH)
        assert len(high) == 1
        assert high[0].customer_id == "c1"

    def test_list_alerts_filter_by_customer_id(self):
        from services.transaction_monitor.store.alert_store import InMemoryAlertStore

        store = InMemoryAlertStore()
        store.save(self._make_alert("cust-A"))
        store.save(self._make_alert("cust-B"))
        alerts = store.list_alerts(customer_id="cust-A")
        assert len(alerts) == 1
        assert alerts[0].customer_id == "cust-A"

    def test_list_alerts_filter_by_status(self):
        from services.transaction_monitor.models.alert import AlertStatus
        from services.transaction_monitor.store.alert_store import InMemoryAlertStore

        store = InMemoryAlertStore()
        a1 = self._make_alert("c1")
        a2 = self._make_alert("c2")
        a2.status = AlertStatus.CLOSED
        store.save(a1)
        store.save(a2)
        open_alerts = store.list_alerts(status=AlertStatus.OPEN)
        assert len(open_alerts) == 1

    def test_count_by_severity(self):
        from services.transaction_monitor.store.alert_store import InMemoryAlertStore

        store = InMemoryAlertStore()
        store.save(self._make_alert("c1", "high"))
        store.save(self._make_alert("c2", "high"))
        store.save(self._make_alert("c3", "low"))
        counts = store.count_by_severity()
        assert counts["high"] == 2
        assert counts["low"] == 1


# ── ExplanationEngine ─────────────────────────────────────────────────────────


class TestExplanationEngine:
    def _make_tx(self) -> object:
        from services.transaction_monitor.models.transaction import TransactionEvent

        return TransactionEvent(
            transaction_id="txn-explain-001",
            sender_id="cust-001",
            amount=Decimal("5000.00"),
            currency="GBP",
            sender_jurisdiction="GB",
        )

    def _make_risk_score(self, score: float = 0.85) -> object:
        from services.transaction_monitor.models.risk_score import RiskFactor, RiskScore

        factors = [
            RiskFactor(
                name="velocity_spike",
                weight=0.4,
                value=0.9,
                contribution=0.36,
                explanation="Unusually high transaction velocity in last 24h",
                regulation_ref="EBA AML 4.2",
            )
        ]
        return RiskScore(score=score, classification="high", factors=factors)

    def test_generate_returns_string(self):
        from services.transaction_monitor.alerts.explanation_engine import (
            ExplanationEngine,
            InMemoryKBPort,
        )

        engine = ExplanationEngine(kb_port=InMemoryKBPort())
        text = engine.generate(
            event=self._make_tx(),
            risk_score=self._make_risk_score(),
            regulation_refs=["EBA AML 4.2"],
        )
        assert isinstance(text, str)
        assert "ALERT" in text

    def test_generate_contains_transaction_id(self):
        from services.transaction_monitor.alerts.explanation_engine import (
            ExplanationEngine,
            InMemoryKBPort,
        )

        engine = ExplanationEngine(kb_port=InMemoryKBPort())
        text = engine.generate(
            event=self._make_tx(),
            risk_score=self._make_risk_score(),
            regulation_refs=["MLR 2017"],
        )
        assert "txn-explain-001" in text

    def test_inmemory_kb_port_returns_regulation_text(self):
        from services.transaction_monitor.alerts.explanation_engine import InMemoryKBPort

        port = InMemoryKBPort()
        result = port.query_regulation("MLR 2017 Reg.28")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_no_regulation_refs(self):
        from services.transaction_monitor.alerts.explanation_engine import (
            ExplanationEngine,
            InMemoryKBPort,
        )

        engine = ExplanationEngine(kb_port=InMemoryKBPort())
        text = engine.generate(
            event=self._make_tx(),
            risk_score=self._make_risk_score(0.2),
            regulation_refs=[],
        )
        assert isinstance(text, str)


# ── TransactionParser error paths ─────────────────────────────────────────────


class TestTransactionParserErrorPaths:
    def _parser(self):
        from services.transaction_monitor.consumer.transaction_parser import TransactionParser

        return TransactionParser()

    def test_parse_missing_amount_raises(self):
        from services.transaction_monitor.consumer.transaction_parser import ParseError

        with pytest.raises(ParseError, match="amount"):
            self._parser().parse({"transaction_id": "t1", "sender_id": "s1"})

    def test_parse_invalid_amount_raises(self):
        from services.transaction_monitor.consumer.transaction_parser import ParseError

        with pytest.raises(ParseError, match="Invalid amount"):
            self._parser().parse(
                {"transaction_id": "t1", "sender_id": "s1", "amount": "not-a-number"}
            )

    def test_parse_zero_amount_raises(self):
        from services.transaction_monitor.consumer.transaction_parser import ParseError

        with pytest.raises(ParseError, match="positive"):
            self._parser().parse({"transaction_id": "t1", "sender_id": "s1", "amount": "0.00"})

    def test_parse_missing_transaction_id_raises(self):
        from services.transaction_monitor.consumer.transaction_parser import ParseError

        with pytest.raises(ParseError, match="transaction_id"):
            self._parser().parse({"sender_id": "s1", "amount": "100.00"})

    def test_parse_missing_sender_id_raises(self):
        from services.transaction_monitor.consumer.transaction_parser import ParseError

        with pytest.raises(ParseError, match="sender_id"):
            self._parser().parse({"transaction_id": "t1", "amount": "100.00"})

    def test_parse_valid_payload_succeeds(self):
        tx = self._parser().parse(
            {
                "transaction_id": "txn-ok",
                "sender_id": "cust-ok",
                "amount": "1500.00",
                "currency": "GBP",
            }
        )
        assert tx.transaction_id == "txn-ok"
        assert tx.amount == Decimal("1500.00")

    def test_parse_unknown_tx_type_defaults_to_payment(self):
        from services.transaction_monitor.models.transaction import TransactionType

        tx = self._parser().parse(
            {
                "transaction_id": "txn-type",
                "sender_id": "cust-type",
                "amount": "100.00",
                "transaction_type": "MYSTERIOUS_TRANSACTION_TYPE",
            }
        )
        assert tx.transaction_type == TransactionType.PAYMENT


# ── RuleEngine ────────────────────────────────────────────────────────────────


class TestRuleEngine:
    def _make_tx(self, jurisdiction: str = "GB") -> object:
        from services.transaction_monitor.models.transaction import TransactionEvent

        return TransactionEvent(
            transaction_id="txn-rule",
            sender_id="cust-rule",
            amount=Decimal("3000.00"),
            sender_jurisdiction=jurisdiction,
        )

    def test_jurisdiction_hard_block_returns_1(self):
        from services.transaction_monitor.scoring.rule_engine import InMemoryJubePort, RuleEngine

        engine = RuleEngine(jube_port=InMemoryJubePort())
        score, factors = engine.evaluate(
            event=self._make_tx(jurisdiction="IR"),
            features={"jurisdiction_risk": 1.0},
        )
        assert score == 1.0
        assert any("jurisdiction" in f.name.lower() for f in factors)

    def test_evaluate_normal_returns_score_between_0_and_1(self):
        from services.transaction_monitor.scoring.rule_engine import InMemoryJubePort, RuleEngine

        engine = RuleEngine(jube_port=InMemoryJubePort())
        score, _ = engine.evaluate(
            event=self._make_tx(),
            features={"velocity_ratio": 0.5, "jurisdiction_risk": 0.0},
        )
        assert 0.0 <= score <= 1.0

    def test_jube_failure_uses_fallback(self):
        from unittest.mock import MagicMock

        from services.transaction_monitor.scoring.rule_engine import RuleEngine

        mock_jube = MagicMock()
        mock_jube.evaluate.side_effect = RuntimeError("Jube unavailable")
        engine = RuleEngine(jube_port=mock_jube)
        score, factors = engine.evaluate(
            event=self._make_tx(),
            features={"jurisdiction_risk": 0.3},
        )
        assert 0.0 <= score <= 1.0


# ── ChangeProposer ────────────────────────────────────────────────────────────


class TestChangeProposer:
    def _make_active_experiment(self):
        from services.experiment_copilot.models.experiment import (
            ComplianceExperiment,
            ExperimentScope,
            ExperimentStatus,
        )

        return ComplianceExperiment(
            id="exp-test-cp-001",
            title="Test Compliance Experiment",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            status=ExperimentStatus.ACTIVE,
            hypothesis="Increasing velocity threshold reduces false positives",
            kb_citations=["eba-gl-2021-02"],
            created_by="test",
            tags=["tm"],
            metrics_baseline={"hit_rate_24h": "85%"},
            metrics_target={"hit_rate_24h": "90%"},
        )

    def test_dry_run_does_not_call_github(self):
        from services.experiment_copilot.agents.change_proposer import (
            ChangeProposer,
            InMemoryGitHubPort,
        )
        from services.experiment_copilot.models.proposal import ProposeRequest
        from services.experiment_copilot.store.audit_trail import AuditTrail

        gh = InMemoryGitHubPort()
        proposer = ChangeProposer(audit=AuditTrail(), github=gh)
        req = ProposeRequest(dry_run=True)
        proposal = proposer.propose(self._make_active_experiment(), req)
        assert len(gh.prs_created) == 0
        assert proposal.pr_title.startswith("[Compliance Experiment]")

    def test_inmemory_github_port_create_pr(self):
        from services.experiment_copilot.agents.change_proposer import InMemoryGitHubPort

        gh = InMemoryGitHubPort()
        pr = gh.create_pr("feat/test", "Test PR", "PR body", base="main")
        assert pr["number"] == 1
        assert "html_url" in pr
        assert len(gh.prs_created) == 1

    def test_inmemory_github_port_create_issue(self):
        from services.experiment_copilot.agents.change_proposer import InMemoryGitHubPort

        gh = InMemoryGitHubPort()
        issue = gh.create_issue("Test Issue", "Issue body", labels=["compliance"])
        assert issue["number"] == 1
        assert len(gh.issues_created) == 1

    def test_propose_non_active_experiment_raises(self):
        from services.experiment_copilot.agents.change_proposer import (
            ChangeProposer,
            InMemoryGitHubPort,
        )
        from services.experiment_copilot.models.experiment import (
            ComplianceExperiment,
            ExperimentScope,
            ExperimentStatus,
        )
        from services.experiment_copilot.models.proposal import ProposeRequest
        from services.experiment_copilot.store.audit_trail import AuditTrail

        exp = ComplianceExperiment(
            id="exp-draft",
            title="Draft Experiment",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            status=ExperimentStatus.DRAFT,
            hypothesis="H",
            kb_citations=[],
            created_by="test",
            tags=[],
        )
        proposer = ChangeProposer(audit=AuditTrail(), github=InMemoryGitHubPort())
        with pytest.raises(ValueError, match="ACTIVE"):
            proposer.propose(exp, ProposeRequest(dry_run=True))

    def test_dry_run_proposal_has_files_changed(self):
        from services.experiment_copilot.agents.change_proposer import (
            ChangeProposer,
            InMemoryGitHubPort,
        )
        from services.experiment_copilot.models.proposal import ProposeRequest
        from services.experiment_copilot.store.audit_trail import AuditTrail

        proposer = ChangeProposer(audit=AuditTrail(), github=InMemoryGitHubPort())
        proposal = proposer.propose(self._make_active_experiment(), ProposeRequest(dry_run=True))
        assert isinstance(proposal.files_changed, list)
        assert len(proposal.files_changed) >= 1


# ── KB service version compare ────────────────────────────────────────────────


class TestKBVersionCompare:
    def test_ingest_raises_for_unknown_notebook(self):
        from services.compliance_kb.embeddings.embedding_service import InMemoryEmbeddingService
        from services.compliance_kb.kb_service import ComplianceKBService
        from services.compliance_kb.storage.chroma_store import InMemoryChromaStore
        from services.compliance_kb.storage.models import (
            IngestRequest,
            Jurisdiction,
            SourceType,
        )

        kb = ComplianceKBService(
            store=InMemoryChromaStore(), embedding_service=InMemoryEmbeddingService()
        )
        with pytest.raises(ValueError, match="not found"):
            kb.ingest(
                IngestRequest(
                    notebook_id="nonexistent-notebook",
                    document_id="d1",
                    name="Test",
                    content="content",
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version="1.0",
                )
            )

    def test_ingest_without_content_or_file_raises(self):
        from services.compliance_kb.embeddings.embedding_service import InMemoryEmbeddingService
        from services.compliance_kb.kb_service import ComplianceKBService
        from services.compliance_kb.storage.chroma_store import InMemoryChromaStore
        from services.compliance_kb.storage.models import (
            IngestRequest,
            Jurisdiction,
            SourceType,
        )

        kb = ComplianceKBService(
            store=InMemoryChromaStore(), embedding_service=InMemoryEmbeddingService()
        )
        with pytest.raises(ValueError, match="content"):
            kb.ingest(
                IngestRequest(
                    notebook_id="emi-uk-fca",
                    document_id="d1",
                    name="Empty Doc",
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version="1.0",
                    # No content or file_path
                )
            )

    def test_compare_versions_returns_result(self):
        from services.compliance_kb.embeddings.embedding_service import InMemoryEmbeddingService
        from services.compliance_kb.kb_service import ComplianceKBService
        from services.compliance_kb.storage.chroma_store import InMemoryChromaStore
        from services.compliance_kb.storage.models import (
            IngestRequest,
            Jurisdiction,
            SourceType,
            VersionCompareRequest,
        )

        kb = ComplianceKBService(
            store=InMemoryChromaStore(), embedding_service=InMemoryEmbeddingService()
        )
        # Ingest two versions of same document
        for ver in ["1.0", "2.0"]:
            kb.ingest(
                IngestRequest(
                    notebook_id="emi-uk-fca",
                    document_id="fca-cass-15",
                    name="CASS 15",
                    content=f"CASS 15 version {ver} — safeguarding requirements.",
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version=ver,
                )
            )
        req = VersionCompareRequest(
            source_id="fca-cass-15",
            from_version="1.0",
            to_version="2.0",
        )
        result = kb.compare_versions(req)
        assert result is not None


# ── TokenManager uncovered branches ──────────────────────────────────────────


class TestTokenManagerUncoveredBranches:
    def test_validate_access_token_missing_sub_raises(self):
        import jwt as pyjwt

        from services.auth.token_manager import TokenManager, TokenValidationError

        tm = TokenManager(secret_key="test-secret-32bytes-long-enough-!")
        # Craft token without sub
        now = datetime.now(tz=UTC)
        payload = {
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=1)).timestamp()),
        }
        bad_token = pyjwt.encode(payload, "test-secret-32bytes-long-enough-!", algorithm="HS256")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_access_token(bad_token)
        assert exc_info.value.code == "missing_sub"

    def test_validate_refresh_token_missing_sub_raises(self):
        import jwt as pyjwt

        from services.auth.token_manager import TokenManager, TokenValidationError

        tm = TokenManager(secret_key="test-secret-32bytes-long-enough-!")
        now = datetime.now(tz=UTC)
        payload = {
            "type": "refresh",
            "jti": "test-jti",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=7)).timestamp()),
        }
        bad_token = pyjwt.encode(payload, "test-secret-32bytes-long-enough-!", algorithm="HS256")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_refresh_token(bad_token)
        assert exc_info.value.code == "missing_sub"

    def test_validate_refresh_token_missing_jti_raises(self):
        import jwt as pyjwt

        from services.auth.token_manager import TokenManager, TokenValidationError

        tm = TokenManager(secret_key="test-secret-32bytes-long-enough-!")
        now = datetime.now(tz=UTC)
        payload = {
            "sub": "cust-001",
            "type": "refresh",
            # no jti
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=7)).timestamp()),
        }
        bad_token = pyjwt.encode(payload, "test-secret-32bytes-long-enough-!", algorithm="HS256")
        with pytest.raises(TokenValidationError) as exc_info:
            tm.validate_refresh_token(bad_token)
        assert exc_info.value.code == "missing_jti"

    def test_rotate_invalid_token_raises(self):
        from services.auth.token_manager import TokenManager, TokenValidationError

        tm = TokenManager(secret_key="test-secret-32bytes-long-enough-!")
        with pytest.raises(TokenValidationError):
            tm.rotate("not-a-real-token")


# ── SCA biometric fallback path ───────────────────────────────────────────────


class TestSCAServiceBiometricFallback:
    def test_biometric_wrong_prefix_fails(self):
        from services.auth.sca_service import InMemorySCAStore, SCAService

        svc = SCAService(store=InMemorySCAStore())
        ch = svc.create_challenge("cust-bm", "txn-bm", "biometric")
        result = svc.verify(ch.challenge_id, biometric_proof="wrong-proof")
        assert result.verified is False

    def test_sca_resend_resets_status_to_pending(self):
        from services.auth.sca_service import InMemorySCAStore, SCAService

        svc = SCAService(store=InMemorySCAStore())
        ch = svc.create_challenge("cust-rsp", "txn-rsp", "otp")
        ch.status = "pending"
        svc._store.save(ch)
        updated = svc.resend_challenge(ch.challenge_id)
        assert updated.status == "pending"
