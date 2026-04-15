"""
tests/test_sprint15_coverage.py — Sprint 15 GAP-3 coverage boost
Targets 57+ uncovered lines across 6 modules to push from 88.56% → ≥89%.

Modules targeted:
  services/transaction_monitor/scoring/velocity_tracker.py  (RedisVelocityTracker: 30 lines)
  services/experiment_copilot/agents/experiment_designer.py (HTTPKBPort: 5 lines)
  services/swarm/orchestrator.py                            (uncovered branches: 8 lines)
  services/repo_watch/maturity_evaluator.py                 (PROD gates: 4 lines)
  services/aml/redis_velocity_tracker.py                    (reset() method: 2 lines)
  services/swarm/agents/product_limits_agent.py             (daily/monthly limits: 6 lines)
  services/design_pipeline/orchestrator.py                  (OllamaLLM success path: 2 lines)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
import pytest

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse
from services.aml.redis_velocity_tracker import RedisVelocityTracker as AMLRedisTracker
from services.repo_watch.config import (
    CriticalIssueLabels,
    DevCandidateThresholds,
    ProdCandidateThresholds,
    RepoWatchConfig,
    WatchedRepo,
)
from services.repo_watch.github_client import RepoStats
from services.repo_watch.maturity_evaluator import MaturityLevel, evaluate_maturity
from services.swarm.agents.base_agent import BaseAgent
from services.swarm.agents.product_limits_agent import ProductLimitsAgent
from services.swarm.orchestrator import SwarmOrchestrator

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_task(**overrides) -> AgentTask:
    defaults = dict(
        task_id="task-s15-001",
        event_type="payment",
        tier=3,
        payload={},
        product="sepa_transfer",
        jurisdiction="EU",
        customer_id="cust-s15-001",
        risk_context={},
        created_at=datetime.now(UTC),
        playbook_id="default",
    )
    defaults.update(overrides)
    return AgentTask(**defaults)


def _make_response(**overrides) -> AgentResponse:
    defaults = dict(
        agent_name="test_agent",
        case_id="task-s15-001",
        signal_type="test",
        risk_score=0.1,
        confidence=0.9,
        decision_hint="clear",
        reason_summary="Test response",
        evidence_refs=[],
        token_cost=0,
        latency_ms=0,
    )
    defaults.update(overrides)
    return AgentResponse(**defaults)


def _make_repo_config() -> RepoWatchConfig:
    return RepoWatchConfig(
        repos=(WatchedRepo(owner="testorg", repo="testrepo"),),
        dev_candidate=DevCandidateThresholds(),
        prod_candidate=ProdCandidateThresholds(),
        critical_issue_labels=CriticalIssueLabels(),
    )


def _make_stats(**overrides) -> RepoStats:
    defaults = dict(
        owner="testorg",
        repo="testrepo",
        stars=20,
        forks=4,
        open_issues=2,
        open_bug_issues=1,
        contributors_count=6,
        last_commit_date=datetime.now(UTC) - timedelta(days=1),
        default_branch="main",
        license_spdx="MIT",
        is_archived=False,
        has_ci=True,
        fetched_at=datetime.now(UTC),
    )
    defaults.update(overrides)
    return RepoStats(**defaults)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: RedisVelocityTracker (TM scoring)
# services/transaction_monitor/scoring/velocity_tracker.py — 30 lines
# Lines: 86-90, 93-107, 110-115, 118-120, 123-126, 129-130
# ─────────────────────────────────────────────────────────────────────────────


def _build_tm_redis_tracker():
    """Build a RedisVelocityTracker with fully mocked redis, covering __init__."""
    mock_redis_lib = MagicMock()
    mock_client = MagicMock()
    mock_pipe = MagicMock()

    mock_redis_lib.from_url.return_value = mock_client
    mock_client.pipeline.return_value = mock_pipe
    # pipeline is used as returned mock; each method returns the pipe for chaining
    mock_pipe.zadd.return_value = None
    mock_pipe.zremrangebyscore.return_value = None
    mock_pipe.expire.return_value = None
    mock_pipe.incrbyfloat.return_value = None
    mock_pipe.execute.return_value = [1, 0, True, 10.0, True]

    mock_client.zcount.return_value = 3
    mock_client.get.return_value = "200.00"

    # Patch sys.modules so `import redis as redis_lib` inside __init__ sees our mock
    saved = sys.modules.get("redis")
    sys.modules["redis"] = mock_redis_lib
    try:
        from services.transaction_monitor.scoring.velocity_tracker import RedisVelocityTracker

        tracker = RedisVelocityTracker(redis_url="redis://localhost:6379/0")
    finally:
        if saved is None:
            sys.modules.pop("redis", None)
        else:
            sys.modules["redis"] = saved

    # Replace internal client with our configured mock
    tracker._redis = mock_client
    return tracker


class TestTMRedisVelocityTrackerInit:
    """Covers __init__ (lines 86-90)."""

    def test_init_creates_instance_with_config(self):
        tracker = _build_tm_redis_tracker()
        assert tracker is not None
        assert tracker._redis is not None
        assert tracker._config is not None


class TestTMRedisVelocityTrackerRecord:
    """Covers record() (lines 93-107)."""

    def test_record_calls_pipeline_for_all_windows(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-s15-001",
            amount=Decimal("150.00"),
            sender_id="cust-gb-001",
            sender_jurisdiction="GB",
        )
        tracker.record(event)
        # Pipeline is called once per window (3 windows: 1h, 24h, 7d)
        assert tracker._redis.pipeline.call_count == 3

    def test_record_with_receiver_jurisdiction(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-s15-002",
            amount=Decimal("500.00"),
            sender_id="cust-de-001",
            sender_jurisdiction="DE",
            receiver_jurisdiction="FR",
        )
        tracker.record(event)
        assert tracker._redis.pipeline.call_count == 3


class TestTMRedisVelocityTrackerGetCount:
    """Covers get_count() (lines 110-115)."""

    def test_get_count_known_window(self):
        tracker = _build_tm_redis_tracker()
        count = tracker.get_count("cust-001", "1h")
        assert count == 3  # matches mock_client.zcount.return_value

    def test_get_count_24h_window(self):
        tracker = _build_tm_redis_tracker()
        count = tracker.get_count("cust-001", "24h")
        assert isinstance(count, int)

    def test_get_count_7d_window(self):
        tracker = _build_tm_redis_tracker()
        count = tracker.get_count("cust-001", "7d")
        assert isinstance(count, int)

    def test_get_count_unknown_window_uses_default_ttl(self):
        tracker = _build_tm_redis_tracker()
        # Unknown window — still calls zcount with a computed timestamp
        count = tracker.get_count("cust-001", "30d")
        assert isinstance(count, int)


class TestTMRedisVelocityTrackerGetCumulativeAmount:
    """Covers get_cumulative_amount() (lines 118-120)."""

    def test_get_cumulative_amount_with_stored_value(self):
        tracker = _build_tm_redis_tracker()
        tracker._redis.get.return_value = "750.50"
        amount = tracker.get_cumulative_amount("cust-001", "24h")
        assert amount == Decimal("750.50")

    def test_get_cumulative_amount_when_key_missing(self):
        tracker = _build_tm_redis_tracker()
        tracker._redis.get.return_value = None
        amount = tracker.get_cumulative_amount("cust-001", "7d")
        assert amount == Decimal("0")


class TestTMRedisVelocityTrackerIsHardBlocked:
    """Covers is_hard_blocked() (lines 123-126)."""

    def test_blocked_sender_jurisdiction(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-blocked-001",
            amount=Decimal("100.00"),
            sender_id="cust-ru",
            sender_jurisdiction="RU",
        )
        assert tracker.is_hard_blocked(event) is True

    def test_blocked_receiver_jurisdiction(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-blocked-002",
            amount=Decimal("100.00"),
            sender_id="cust-gb",
            sender_jurisdiction="GB",
            receiver_jurisdiction="IR",
        )
        assert tracker.is_hard_blocked(event) is True

    def test_clean_jurisdictions_not_blocked(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-clean-001",
            amount=Decimal("100.00"),
            sender_id="cust-de",
            sender_jurisdiction="DE",
            receiver_jurisdiction="FR",
        )
        assert tracker.is_hard_blocked(event) is False

    def test_no_receiver_jurisdiction_only_sender_checked(self):
        from services.transaction_monitor.models.transaction import TransactionEvent

        tracker = _build_tm_redis_tracker()
        event = TransactionEvent(
            transaction_id="tx-no-recv",
            amount=Decimal("50.00"),
            sender_id="cust-gb",
            sender_jurisdiction="GB",
        )
        assert tracker.is_hard_blocked(event) is False


class TestTMRedisVelocityTrackerRequiresEdd:
    """Covers requires_edd() (lines 129-130)."""

    def test_requires_edd_above_threshold(self):
        tracker = _build_tm_redis_tracker()
        # EDD threshold for individual is GBP 10,000; 24h cumulative is 15,000
        tracker._redis.get.return_value = "15000.00"
        assert tracker.requires_edd("cust-high") is True

    def test_requires_edd_below_threshold(self):
        tracker = _build_tm_redis_tracker()
        tracker._redis.get.return_value = "500.00"
        assert tracker.requires_edd("cust-low") is False

    def test_requires_edd_exactly_at_threshold(self):
        tracker = _build_tm_redis_tracker()
        tracker._redis.get.return_value = "10000.00"
        # At exactly threshold → True (>=)
        assert tracker.requires_edd("cust-boundary") is True


# ─────────────────────────────────────────────────────────────────────────────
# Section 2: HTTPKBPort
# services/experiment_copilot/agents/experiment_designer.py — 5 lines (73-85)
# ─────────────────────────────────────────────────────────────────────────────


class TestHTTPKBPort:
    """Tests for HTTPKBPort.query_kb() with mocked httpx."""

    def test_query_kb_success_returns_answer_and_citations(self):
        from services.experiment_copilot.agents.experiment_designer import HTTPKBPort

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "answer": "PSD2 requires strong customer authentication for remote payments.",
            "citations": [{"source_id": "eba-gl-2021-02", "title": "EBA Guidelines"}],
        }
        mock_response.raise_for_status.return_value = None

        mock_client_ctx = MagicMock()
        mock_client_ctx.__enter__ = MagicMock(return_value=mock_client_ctx)
        mock_client_ctx.__exit__ = MagicMock(return_value=False)
        mock_client_ctx.post.return_value = mock_response

        with patch("httpx.Client", return_value=mock_client_ctx):
            port = HTTPKBPort(api_base="http://localhost:8000")
            result = port.query_kb(
                notebook_id="emi-uk-fca",
                question="What are PSD2 SCA requirements?",
                max_citations=3,
            )

        assert result["answer"].startswith("PSD2")
        assert len(result["citations"]) == 1
        assert result["citations"][0]["source_id"] == "eba-gl-2021-02"

    def test_make_kb_port_returns_http_port_when_adapter_is_http(self):
        from services.experiment_copilot.agents.experiment_designer import HTTPKBPort, make_kb_port

        with patch.dict(
            "os.environ", {"KB_ADAPTER": "http", "KB_API_BASE": "http://api.test:9000"}
        ):
            port = make_kb_port()
        assert isinstance(port, HTTPKBPort)

    def test_make_kb_port_returns_http_port_when_adapter_is_production(self):
        from services.experiment_copilot.agents.experiment_designer import HTTPKBPort, make_kb_port

        with patch.dict("os.environ", {"KB_ADAPTER": "production"}):
            port = make_kb_port()
        assert isinstance(port, HTTPKBPort)


# ─────────────────────────────────────────────────────────────────────────────
# Section 3: SwarmOrchestrator uncovered branches
# services/swarm/orchestrator.py — 8 lines (138-141, 165, 198-200, 263)
# ─────────────────────────────────────────────────────────────────────────────


class _FailingAgent(BaseAgent):
    """Test double — always raises RuntimeError."""

    @property
    def agent_name(self) -> str:
        return "failing_agent"

    @property
    def signal_type(self) -> str:
        return "test_signal"

    async def analyze(self, task: AgentTask) -> AgentResponse:
        raise RuntimeError("Simulated compliance agent failure")


class TestSwarmOrchestratorUncoveredBranches:
    async def test_star_topology_agent_failure_produces_manual_review(self):
        """Lines 138-141: failing agent in star topology → fallback manual_review response."""
        orch = SwarmOrchestrator()
        task = _make_task()
        responses = await orch._star(task, [_FailingAgent()])

        assert len(responses) == 1
        assert responses[0].decision_hint == "manual_review"
        assert "Agent failed" in responses[0].reason_summary
        assert responses[0].risk_score == 0.5
        assert responses[0].confidence == 0.1

    async def test_hierarchy_empty_agent_list_returns_empty(self):
        """Line 165: _hierarchy() with no agents returns empty list immediately."""
        orch = SwarmOrchestrator()
        task = _make_task()
        result = await orch._hierarchy(task, [])
        assert result == []

    async def test_ring_topology_agent_exception_produces_fallback(self):
        """Lines 198-200: failing agent in ring topology → fallback response, not propagated."""
        orch = SwarmOrchestrator()
        task = _make_task()
        responses = await orch._ring(task, [_FailingAgent()])

        assert len(responses) == 1
        assert responses[0].decision_hint == "manual_review"
        assert "failed" in responses[0].reason_summary.lower()

    def test_aggregate_high_risk_clear_hint_returns_decline(self):
        """Line 263: no blocks, no warnings, risk >= 0.6 → 'decline'."""
        orch = SwarmOrchestrator()
        # risk_score=0.8, decision_hint='clear' — no blocks, not enough warnings for Rule 3
        responses = [_make_response(risk_score=0.8, decision_hint="clear", confidence=0.95)]
        decision = orch._aggregate(responses)
        assert decision == "decline"

    def test_aggregate_moderate_risk_returns_manual_review(self):
        """Rule 5: 0.25 <= risk < 0.6 → 'manual_review'."""
        orch = SwarmOrchestrator()
        responses = [_make_response(risk_score=0.4, decision_hint="clear")]
        decision = orch._aggregate(responses)
        assert decision == "manual_review"

    def test_aggregate_empty_responses_returns_manual_review(self):
        """No responses → 'manual_review'."""
        orch = SwarmOrchestrator()
        assert orch._aggregate([]) == "manual_review"


# ─────────────────────────────────────────────────────────────────────────────
# Section 4: MaturityEvaluator PROD_CANDIDATE gate failures
# services/repo_watch/maturity_evaluator.py — 4 lines (101, 105, 113, 115)
# ─────────────────────────────────────────────────────────────────────────────


class TestMaturityEvaluatorProdGates:
    """Each test triggers exactly one PROD_CANDIDATE gate failure line."""

    def test_prod_gate_too_few_contributors_returns_dev_candidate(self):
        """Line 101: contributors_count < prod min_contributors (5) → DEV_CANDIDATE."""
        config = _make_repo_config()
        # 4 passes DEV (min=3) but fails PROD (min=5)
        stats = _make_stats(
            contributors_count=4, open_bug_issues=1, has_ci=True, license_spdx="MIT"
        )
        result = evaluate_maturity(stats, config, weeks_stable=12)
        assert result.level == MaturityLevel.DEV_CANDIDATE
        assert any("contributors" in r and "prod" in r for r in result.reasons)

    def test_prod_gate_too_many_open_bugs_returns_dev_candidate(self):
        """Line 105: open_bug_issues > prod max_open_bug_issues (2) → DEV_CANDIDATE."""
        config = _make_repo_config()
        # 3 passes DEV (max=5) but fails PROD (max=2)
        stats = _make_stats(
            contributors_count=6, open_bug_issues=3, has_ci=True, license_spdx="Apache-2.0"
        )
        result = evaluate_maturity(stats, config, weeks_stable=12)
        assert result.level == MaturityLevel.DEV_CANDIDATE
        assert any("open bug" in r and "prod" in r for r in result.reasons)

    def test_prod_gate_no_ci_returns_dev_candidate(self):
        """Line 113: has_ci=False → DEV_CANDIDATE."""
        config = _make_repo_config()
        stats = _make_stats(
            contributors_count=6,
            open_bug_issues=0,
            has_ci=False,
            license_spdx="MIT",
        )
        result = evaluate_maturity(stats, config, weeks_stable=12)
        assert result.level == MaturityLevel.DEV_CANDIDATE
        assert any("CI" in r or "ci" in r.lower() for r in result.reasons)

    def test_prod_gate_no_license_returns_dev_candidate(self):
        """Line 115: license_spdx=None → DEV_CANDIDATE."""
        config = _make_repo_config()
        stats = _make_stats(
            contributors_count=6,
            open_bug_issues=0,
            has_ci=True,
            license_spdx=None,
        )
        result = evaluate_maturity(stats, config, weeks_stable=12)
        assert result.level == MaturityLevel.DEV_CANDIDATE
        assert any("license" in r.lower() for r in result.reasons)

    def test_all_prod_gates_pass_returns_prod_candidate(self):
        """Baseline: all gates pass → PROD_CANDIDATE."""
        config = _make_repo_config()
        stats = _make_stats(
            contributors_count=6,
            open_bug_issues=0,
            has_ci=True,
            license_spdx="MIT",
        )
        result = evaluate_maturity(stats, config, weeks_stable=13)
        assert result.level == MaturityLevel.PROD_CANDIDATE


# ─────────────────────────────────────────────────────────────────────────────
# Section 5: AML RedisVelocityTracker reset()
# services/aml/redis_velocity_tracker.py — 2 lines (161-162)
# ─────────────────────────────────────────────────────────────────────────────


class TestAMLRedisVelocityTrackerReset:
    @pytest.fixture
    def tracker(self):
        return AMLRedisTracker(fakeredis.FakeRedis())

    def test_reset_clears_recorded_transactions(self, tracker):
        """Lines 161-162: reset() calls redis.delete() — recorded data disappears."""
        tracker.record("cust-reset-s15", Decimal("100.00"))
        tracker.record("cust-reset-s15", Decimal("200.00"))

        _, count_before = tracker.get_daily("cust-reset-s15")
        assert count_before == 2

        tracker.reset("cust-reset-s15")

        _, count_after = tracker.get_daily("cust-reset-s15")
        assert count_after == 0

    def test_reset_on_unknown_customer_does_not_raise(self, tracker):
        """reset() on a customer with no records is safe."""
        tracker.reset("cust-never-recorded")  # must not raise


# ─────────────────────────────────────────────────────────────────────────────
# Section 6: ProductLimitsAgent daily and monthly limit checks
# services/swarm/agents/product_limits_agent.py — 6 lines (90-94, 97-99)
# ─────────────────────────────────────────────────────────────────────────────


class TestProductLimitsAgentDailyMonthlyLimits:
    """Daily and monthly limit branches — not covered by existing tests."""

    async def test_daily_limit_exceeded_adds_signal(self):
        """Lines 90-94: daily_total + amount > daily_max triggers risk + signal."""
        agent = ProductLimitsAgent()
        # sepa_transfer → uses "default" limits: daily_max=25000
        # daily_total=24500, amount=1000 → 25500 > 25000 → triggers
        task = _make_task(
            risk_context={"daily_total_eur": "24500", "monthly_total_eur": "0"},
            payload={"amount_eur": "1000"},
        )
        response = await agent.analyze(task)
        assert "daily" in response.reason_summary.lower() or response.risk_score > 0
        assert "daily_limit_check" in response.evidence_refs

    async def test_monthly_limit_exceeded_adds_signal(self):
        """Lines 97-99: monthly_total + amount > monthly_max triggers risk + signal."""
        agent = ProductLimitsAgent()
        # sepa_transfer → uses "default" limits: monthly_max=100000
        # monthly_total=99500, amount=1000 → 100500 > 100000 → triggers
        task = _make_task(
            risk_context={"daily_total_eur": "0", "monthly_total_eur": "99500"},
            payload={"amount_eur": "1000"},
        )
        response = await agent.analyze(task)
        assert "monthly_limit_check" in response.evidence_refs

    async def test_both_daily_and_monthly_limits_exceeded(self):
        """Both daily and monthly limit branches triggered in one transaction."""
        agent = ProductLimitsAgent()
        task = _make_task(
            risk_context={"daily_total_eur": "24500", "monthly_total_eur": "99500"},
            payload={"amount_eur": "1000"},
        )
        response = await agent.analyze(task)
        assert "daily_limit_check" in response.evidence_refs
        assert "monthly_limit_check" in response.evidence_refs


# ─────────────────────────────────────────────────────────────────────────────
# Section 7: OllamaLLM success path
# services/design_pipeline/orchestrator.py — 2 lines (119-120)
# ─────────────────────────────────────────────────────────────────────────────


class TestOllamaLLMSuccessPath:
    """Lines 119-120: httpx POST succeeds → raise_for_status + return response."""

    async def test_agenerate_returns_ollama_response_text(self):
        from services.design_pipeline.orchestrator import OllamaLLM

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "export default function Button() {}"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            llm = OllamaLLM(base_url="http://localhost:11434")
            result = await llm.agenerate("Generate a React button component")

        assert result == "export default function Button() {}"
        mock_response.raise_for_status.assert_called_once()

    async def test_agenerate_uses_model_name_in_payload(self):
        from services.design_pipeline.orchestrator import OllamaLLM

        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "// generated"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            llm = OllamaLLM(model="codellama:7b")
            await llm.agenerate("prompt text")

        call_kwargs = mock_client.post.call_args
        payload = (
            call_kwargs.kwargs.get("json") or call_kwargs.args[1]
            if len(call_kwargs.args) > 1
            else call_kwargs.kwargs["json"]
        )
        assert payload["model"] == "codellama:7b"


# ─────────────────────────────────────────────────────────────────────────────
# Section 8: GeoRiskAgent uncovered branches
# services/swarm/agents/geo_risk_agent.py — 3 lines (115-116, 153)
# ─────────────────────────────────────────────────────────────────────────────


class TestGeoRiskAgentBranches:
    """Covers cross-border risk boost (115-116) and EU high-risk country path (153)."""

    async def test_cross_border_with_elevated_risk_boosts_score(self):
        """Lines 115-116: cross_border=True AND risk > 0.2 → risk += 0.1, adds signal."""
        from services.swarm.agents.geo_risk_agent import GeoRiskAgent

        agent = GeoRiskAgent()
        # NG is on FATF greylist (risk=0.65), cross_border=True → triggers lines 115-116
        task = _make_task(
            jurisdiction="NG",
            risk_context={"cross_border": True},
        )
        response = await agent.analyze(task)
        assert "cross-border" in response.reason_summary.lower()
        assert response.risk_score > 0.6

    async def test_eu_high_risk_country_returns_moderate_risk(self):
        """Line 153: beneficiary country in _EU_HIGH_RISK (not sanctioned, not FATF greylist)."""
        from services.swarm.agents.geo_risk_agent import GeoRiskAgent

        agent = GeoRiskAgent()
        # BS (Bahamas) is in _EU_HIGH_RISK only — triggers line 153
        task = _make_task(
            jurisdiction="GB",
            payload={"beneficiary_country": "BS"},
            risk_context={"cross_border": False},
        )
        response = await agent.analyze(task)
        assert response.risk_score >= 0.55
        assert "eu_aml_directive" in response.evidence_refs
