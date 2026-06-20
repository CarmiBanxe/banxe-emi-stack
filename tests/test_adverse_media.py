"""
tests/test_adverse_media.py — IMPL-1 adverse-media screening (GAP-064)

Unit (feed safe-stub, matcher, service CLEAR/HIT) + EDD trigger + MANDATORY
MLRO HITL gate (no auto-clear). Reuses real EventStore / HITLService (in-memory)
and fakes for the customer source and Marble case opener.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from services.adverse_media.feed import OpenSanctionsAdjacencyFeed
from services.adverse_media.matcher import AdverseMediaMatcher
from services.adverse_media.models import (
    AdverseMediaArticle,
    ScreeningAction,
)
from services.adverse_media.service import AdverseMediaService
from services.audit_trail.event_store import EventStore
from services.case_management.case_port import CaseRequest, CaseResult, CaseStatus
from services.customer.customer_port import (
    Address,
    CustomerProfile,
    EntityType,
    IndividualProfile,
    LifecycleState,
    RiskLevel,
)
from services.hitl.hitl_port import CaseStatus as HITLCaseStatus
from services.hitl.hitl_service import HITLService


def _profile(risk: RiskLevel = RiskLevel.HIGH) -> CustomerProfile:
    return CustomerProfile(
        customer_id="cust-001",
        entity_type=EntityType.INDIVIDUAL,
        kyc_status="VERIFIED",
        risk_level=risk,
        lifecycle_state=LifecycleState.ONBOARDING,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        individual=IndividualProfile(
            first_name="John",
            last_name="Smith",
            date_of_birth=date(1980, 5, 1),
            nationality="GB",
            address=Address(line1="1 High St", city="London", country="GB"),
        ),
    )


class _StubFeed:
    def __init__(self, articles: list[AdverseMediaArticle]) -> None:
        self._articles = articles

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]:
        return list(self._articles)


class _FakeCustomers:
    def __init__(self, profile: CustomerProfile) -> None:
        self._p = profile

    def get_customer(self, customer_id: str) -> CustomerProfile:
        return self._p


class _FakeOpener:
    def __init__(self) -> None:
        self.requests: list[CaseRequest] = []

    def create_case(self, request: CaseRequest) -> CaseResult:
        self.requests.append(request)
        return CaseResult(
            case_id="marble-123",
            case_reference=request.case_reference,
            status=CaseStatus.OPEN,
            provider="mock",
            created_at=datetime(2026, 6, 20, tzinfo=UTC),
        )


_HIT_ARTICLE = AdverseMediaArticle(
    article_id="a1",
    subject_name="John Smith",
    headline="John Smith charged in fraud probe",
    source="reuters",
    categories=["fraud"],
    subject_dob="1980-05-01",
    subject_jurisdiction="GB",
)
_NOISE_ARTICLE = AdverseMediaArticle(
    article_id="a2",
    subject_name="Zachary Albright",
    headline="Unrelated person wins award",
    source="local",
)


def _service(
    profile: CustomerProfile,
    feed_articles: list[AdverseMediaArticle],
    opener: _FakeOpener | None = None,
    audit: EventStore | None = None,
    hitl: HITLService | None = None,
) -> AdverseMediaService:
    return AdverseMediaService(
        customer_service=_FakeCustomers(profile),
        feed=_StubFeed(feed_articles),
        case_opener=opener or _FakeOpener(),
        audit=audit or EventStore(),
        hitl=hitl or HITLService(),
    )


class TestFeedSafeStub:
    def test_unconfigured_feed_returns_empty_no_secrets(self) -> None:
        # No ADVERSE_MEDIA_FEED_URL → safe stub, no network, no secrets.
        assert OpenSanctionsAdjacencyFeed(feed_url="").fetch("John Smith") == []


class TestMatcher:
    def test_matches_same_person(self) -> None:
        hits = AdverseMediaMatcher().find_hits(_profile(), [_HIT_ARTICLE])
        assert len(hits) == 1
        assert hits[0].composite_score >= Decimal("65")
        assert hits[0].dob_match is True
        assert hits[0].nat_match is True

    def test_ignores_unrelated(self) -> None:
        assert AdverseMediaMatcher().find_hits(_profile(), [_NOISE_ARTICLE]) == []


class TestService:
    def test_clear_when_no_articles(self) -> None:
        res = _service(_profile(), []).screen_customer("cust-001")
        assert res.action is ScreeningAction.CLEAR
        assert res.risk == "NONE"
        assert res.hitl_case_id is None

    def test_hit_opens_marble_case(self) -> None:
        opener = _FakeOpener()
        res = _service(_profile(), [_HIT_ARTICLE], opener=opener).screen_customer("cust-001")
        assert res.action is ScreeningAction.HITL_REVIEW
        assert res.marble_case_id == "marble-123"
        assert len(opener.requests) == 1
        assert opener.requests[0].entity_id == "cust-001"

    def test_hit_appends_audit_event(self) -> None:
        audit = EventStore()
        _service(_profile(), [_HIT_ARTICLE], audit=audit).screen_customer("cust-001")
        events = audit.list_by_entity("cust-001")
        assert any(e.details.get("result") == "hit" for e in events)


class TestHITLGate:
    def test_hit_enqueues_mlro_review_no_auto_clear(self) -> None:
        hitl = HITLService()
        res = _service(_profile(), [_HIT_ARTICLE], hitl=hitl).screen_customer("cust-001")
        assert res.hitl_case_id is not None
        case = hitl.get_case(res.hitl_case_id)
        assert case is not None
        assert case.status is HITLCaseStatus.PENDING  # mandatory review, not auto-cleared


class TestEddTrigger:
    def test_should_screen_high_risk(self) -> None:
        assert AdverseMediaService.should_screen(_profile(RiskLevel.HIGH)) is True

    def test_should_not_screen_low_risk(self) -> None:
        assert AdverseMediaService.should_screen(_profile(RiskLevel.LOW)) is False
