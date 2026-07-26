"""tests/test_compliance_automation/test_periodic_review.py — PeriodicReview tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import time

import pytest

from services.adverse_media.models import (
    AdverseMediaArticle,
    AdverseMediaHit,
    AdverseMediaResult,
    ScreeningAction,
)
from services.compliance_automation.models import (
    CheckStatus,
    ComplianceCheck,
    ComplianceRule,
    InMemoryCheckStore,
    InMemoryReportStore,
    InMemoryRuleStore,
    RuleSeverity,
    RuleType,
)
from services.compliance_automation.periodic_review import PeriodicReview
from services.sanctions_screening.models import MatchConfidence

_NOW = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


def _make_rule(
    rule_id: str,
    rule_type: RuleType,
    logic: str = "aml_threshold",
) -> ComplianceRule:
    return ComplianceRule(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        rule_type=rule_type,
        severity=RuleSeverity.HIGH,
        description="Test",
        evaluation_logic=logic,
        is_active=True,
        version=1,
        created_at=_NOW,
    )


def _make_check(
    check_id: str,
    entity_id: str,
    status: CheckStatus,
) -> ComplianceCheck:
    return ComplianceCheck(
        check_id=check_id,
        entity_id=entity_id,
        rule_id="r-1",
        status=status,
        finding="finding",
        evidence="ev",
        checked_at=_NOW,
    )


@pytest.fixture
def review():
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    return PeriodicReview(rule_store, check_store, report_store), rule_store


@pytest.mark.asyncio
async def test_run_customer_review_empty(review):
    rv, _ = review
    report = await rv.run_customer_review("ent-1")
    assert report.entity_id == "ent-1"
    assert report.overall_status == CheckStatus.PASS
    assert report.checks == ()


@pytest.mark.asyncio
async def test_run_customer_review_with_kyc_rule(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-kyc-1", RuleType.KYC, "kyc_expired"))
    report = await rv.run_customer_review("ent-1")
    assert len(report.checks) == 1
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_customer_review_with_aml_rule(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    report = await rv.run_customer_review("ent-1")
    assert len(report.checks) == 1
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_pep_screening(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-pep-1", RuleType.PEP, "pep_rescreen"))
    report = await rv.run_pep_screening("ent-1")
    assert len(report.checks) == 1
    assert report.entity_id == "ent-1"


@pytest.mark.asyncio
async def test_run_sanctions_screening_pass(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-safe-1", RuleType.SANCTIONS, "aml_threshold"))
    report = await rv.run_sanctions_screening("ent-1")
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_run_sanctions_screening_fail(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-san-1", RuleType.SANCTIONS, "sanctions_hit"))
    report = await rv.run_sanctions_screening("ent-1")
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_all_pass(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.PASS),
        _make_check("c-2", "ent-1", CheckStatus.PASS),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_generate_report_any_fail_gives_fail(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.PASS),
        _make_check("c-2", "ent-1", CheckStatus.FAIL),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_warning_no_fail(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.WARNING),
        _make_check("c-2", "ent-1", CheckStatus.PASS),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.WARNING


@pytest.mark.asyncio
async def test_generate_report_fail_beats_warning(review):
    rv, _ = review
    checks = [
        _make_check("c-1", "ent-1", CheckStatus.WARNING),
        _make_check("c-2", "ent-1", CheckStatus.FAIL),
    ]
    report = await rv.generate_report("ent-1", checks)
    assert report.overall_status == CheckStatus.FAIL


@pytest.mark.asyncio
async def test_generate_report_has_period(review):
    rv, _ = review
    report = await rv.generate_report("ent-1", [])
    assert report.period_start < report.period_end
    delta = report.period_end - report.period_start
    assert delta.days == 30


@pytest.mark.asyncio
async def test_generate_report_saved_to_store(review):
    rv, _ = review
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    rv2 = PeriodicReview(rule_store, check_store, report_store)
    report = await rv2.generate_report("ent-1", [])
    fetched = await report_store.get_report(report.report_id)
    assert fetched is not None


@pytest.mark.asyncio
async def test_run_customer_review_has_report_id(review):
    rv, _ = review
    report = await rv.run_customer_review("ent-1")
    assert len(report.report_id) == 36  # UUID


@pytest.mark.asyncio
async def test_run_pep_screening_no_pep_rules_empty_checks(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    report = await rv.run_pep_screening("ent-1")
    assert len(report.checks) == 0


@pytest.mark.asyncio
async def test_run_sanctions_ignores_aml_rules(review):
    rv, rule_store = review
    await rule_store.save_rule(_make_rule("rule-aml-1", RuleType.AML, "aml_threshold"))
    await rule_store.save_rule(_make_rule("rule-san-1", RuleType.SANCTIONS, "aml_threshold"))
    report = await rv.run_sanctions_screening("ent-1")
    assert len(report.checks) == 1
    assert report.checks[0].rule_id == "rule-san-1"


# ── Adverse-media periodic re-screening (SANDBOX-off by default) ───────────────


def _am_clear() -> AdverseMediaResult:
    return AdverseMediaResult(
        customer_id="ent-1",
        screened_at=_NOW,
        action=ScreeningAction.CLEAR,
        risk="NONE",
    )


def _am_hit() -> AdverseMediaResult:
    article = AdverseMediaArticle(
        article_id="a-1",
        subject_name="Jane Doe",
        headline="Jane Doe charged in fraud investigation",
        source="rss:news.example.com",
        categories=["rss-osint"],
    )
    hit = AdverseMediaHit(
        article=article,
        name_score=Decimal("90"),
        dob_match=False,
        nat_match=True,
        composite_score=Decimal("80"),
        confidence=MatchConfidence.HIGH,
    )
    return AdverseMediaResult(
        customer_id="ent-1",
        screened_at=_NOW,
        action=ScreeningAction.HITL_REVIEW,
        risk="HIGH",
        hits=[hit],
        marble_case_id="marble-1",
        hitl_case_id="hitl-1",  # the SERVICE enqueued MLRO HITL — not the periodic caller
    )


class _FakeAdverseMedia:
    """Records calls; returns a canned result. Raises if constructed to be untouchable."""

    def __init__(self, result: AdverseMediaResult | None = None, *, forbid: bool = False) -> None:
        self._result = result
        self._forbid = forbid
        self.calls: list[tuple[str, str]] = []

    def screen_customer(self, customer_id: str, *, actor_id: str = "system") -> AdverseMediaResult:
        if self._forbid:
            raise AssertionError("adverse-media feed must NOT be called when sandbox-disabled")
        self.calls.append((customer_id, actor_id))
        assert self._result is not None
        return self._result


def _review_with(service: _FakeAdverseMedia) -> PeriodicReview:
    return PeriodicReview(
        InMemoryRuleStore(),
        InMemoryCheckStore(),
        InMemoryReportStore(),
        adverse_media=service,  # type: ignore[arg-type]
    )


@pytest.mark.asyncio
async def test_adverse_media_disabled_by_default_skips_and_never_calls_feed(monkeypatch):
    monkeypatch.delenv("ADVERSE_MEDIA_PERIODIC_ENABLED", raising=False)
    rv = _review_with(_FakeAdverseMedia(forbid=True))
    report = await rv.run_adverse_media_screening("ent-1")
    assert len(report.checks) == 1
    assert report.checks[0].status == CheckStatus.SKIPPED
    assert "sandbox" in report.checks[0].finding.lower()
    assert report.overall_status == CheckStatus.PASS  # SKIPPED never fails a report


@pytest.mark.asyncio
async def test_adverse_media_env_zero_still_disabled(monkeypatch):
    monkeypatch.setenv("ADVERSE_MEDIA_PERIODIC_ENABLED", "0")
    rv = _review_with(_FakeAdverseMedia(forbid=True))
    report = await rv.run_adverse_media_screening("ent-1")
    assert report.checks[0].status == CheckStatus.SKIPPED


@pytest.mark.asyncio
async def test_adverse_media_enabled_clear_gives_pass(monkeypatch):
    monkeypatch.setenv("ADVERSE_MEDIA_PERIODIC_ENABLED", "1")
    fake = _FakeAdverseMedia(_am_clear())
    rv = _review_with(fake)
    report = await rv.run_adverse_media_screening("ent-1")
    assert report.overall_status == CheckStatus.PASS
    assert report.checks[0].status == CheckStatus.PASS
    assert fake.calls == [("ent-1", "cdd_review_agent:periodic")]


@pytest.mark.asyncio
async def test_adverse_media_enabled_hit_gives_warning_not_fail(monkeypatch):
    monkeypatch.setenv("ADVERSE_MEDIA_PERIODIC_ENABLED", "1")
    fake = _FakeAdverseMedia(_am_hit())
    rv = _review_with(fake)
    report = await rv.run_adverse_media_screening("ent-1")
    # Advisory only: a hit is WARNING, never auto-FAIL — the decision is the MLRO
    # HITL case the service enqueued (evidenced by hitl_case_id in the check).
    assert report.overall_status == CheckStatus.WARNING
    assert report.checks[0].status == CheckStatus.WARNING
    assert "hitl_case_id=hitl-1" in report.checks[0].evidence
    assert len(fake.calls) == 1  # MLRO-HITL routing is the SERVICE's responsibility


@pytest.mark.asyncio
async def test_adverse_media_sync_service_does_not_block_loop(monkeypatch):
    monkeypatch.setenv("ADVERSE_MEDIA_PERIODIC_ENABLED", "1")

    class _SlowFake(_FakeAdverseMedia):
        def screen_customer(
            self, customer_id: str, *, actor_id: str = "system"
        ) -> AdverseMediaResult:
            time.sleep(0.01)  # sync work runs in a thread via asyncio.to_thread
            return super().screen_customer(customer_id, actor_id=actor_id)

    rv = _review_with(_SlowFake(_am_clear()))
    report = await rv.run_adverse_media_screening("ent-1")
    assert report.overall_status == CheckStatus.PASS


@pytest.mark.asyncio
async def test_adverse_media_report_is_persisted(monkeypatch):
    monkeypatch.setenv("ADVERSE_MEDIA_PERIODIC_ENABLED", "1")
    report_store = InMemoryReportStore()
    rv = PeriodicReview(
        InMemoryRuleStore(),
        InMemoryCheckStore(),
        report_store,
        adverse_media=_FakeAdverseMedia(_am_clear()),  # type: ignore[arg-type]
    )
    report = await rv.run_adverse_media_screening("ent-1")
    assert await report_store.get_report(report.report_id) is not None
