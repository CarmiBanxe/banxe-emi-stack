"""
services/adverse_media/service.py — AdverseMediaService orchestration
GAP-064 | IMPL-1 | banxe-emi-stack

Onboarding + periodic adverse-media screening for EDD (MLR 2017 Reg.28(3),
FCA SYSC 6.3, I-04). On hit: open a Marble case (reuse case_management),
append an append-only ClickHouse audit event (reuse audit_trail), and enqueue
a MANDATORY MLRO HITL review (reuse hitl) — no auto-clear, no auto-block.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging

from services.adverse_media.feed import OpenSanctionsAdjacencyFeed
from services.adverse_media.matcher import AdverseMediaMatcher, subject_identity
from services.adverse_media.models import (
    AdverseMediaHit,
    AdverseMediaResult,
    CaseOpenerPort,
    NegativeNewsFeed,
    ScreeningAction,
)
from services.audit_trail.event_store import EventStore
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    SourceSystem,
)
from services.case_management.case_port import CasePriority, CaseRequest, CaseResult, CaseType
from services.customer.customer_port import (
    CustomerManagementPort,
    CustomerProfile,
    RiskLevel,
)
from services.hitl.hitl_port import ReviewReason
from services.hitl.hitl_service import HITLService
from services.sanctions_screening.models import MatchConfidence

logger = logging.getLogger(__name__)

# Risk levels at/above which adverse-media screening is triggered (>= I-04 EDD scrutiny).
_SCREEN_RISK_LEVELS = frozenset(
    {RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.VERY_HIGH, RiskLevel.PROHIBITED}
)
_CONFIDENCE_RISK: dict[MatchConfidence, str] = {
    MatchConfidence.HIGH: "HIGH",
    MatchConfidence.MEDIUM: "MEDIUM",
    MatchConfidence.LOW: "LOW",
}
_RISK_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3}


class _LazyMarbleOpener:
    """Default case opener — instantiates MarbleAdapter lazily (needs env at call time)."""

    def create_case(self, request: CaseRequest) -> CaseResult:
        from services.case_management.marble_adapter import MarbleAdapter

        return MarbleAdapter().create_case(request)


class AdverseMediaService:
    """Orchestrates feed → match → (Marble case + audit + MLRO HITL) on hit."""

    def __init__(
        self,
        *,
        customer_service: CustomerManagementPort,
        feed: NegativeNewsFeed | None = None,
        matcher: AdverseMediaMatcher | None = None,
        case_opener: CaseOpenerPort | None = None,
        audit: EventStore | None = None,
        hitl: HITLService | None = None,
    ) -> None:
        self._customers = customer_service
        self._feed: NegativeNewsFeed = feed or OpenSanctionsAdjacencyFeed()
        self._matcher = matcher or AdverseMediaMatcher()
        self._case_opener: CaseOpenerPort = case_opener or _LazyMarbleOpener()
        self._audit = audit or EventStore()
        self._hitl = hitl or HITLService()

    @staticmethod
    def should_screen(profile: CustomerProfile) -> bool:
        """Trigger adverse-media screening at onboarding for risk >= I-04 scrutiny."""
        return profile.risk_level in _SCREEN_RISK_LEVELS

    def screen_customer(self, customer_id: str, *, actor_id: str = "system") -> AdverseMediaResult:
        profile = self._customers.get_customer(customer_id)
        name, _dob, jurisdiction = subject_identity(profile)
        articles = self._feed.fetch(name, jurisdiction=jurisdiction)
        hits = self._matcher.find_hits(profile, articles)
        now = datetime.now(UTC)

        if not hits:
            self._audit.append(
                category=EventCategory.COMPLIANCE,
                severity=EventSeverity.INFO,
                action=AuditAction.READ,
                entity_type="customer",
                entity_id=customer_id,
                actor_id=actor_id,
                details={"screen": "adverse_media", "result": "clear", "articles": len(articles)},
                source=SourceSystem.API,
            )
            return AdverseMediaResult(
                customer_id=customer_id,
                screened_at=now,
                action=ScreeningAction.CLEAR,
                risk="NONE",
            )

        risk = _max_risk(hits)
        marble_case_id = self._open_case(profile, hits, risk)
        hitl_case_id = self._enqueue_mlro(profile, hits)
        self._audit.append(
            category=EventCategory.AML,
            severity=EventSeverity.WARNING,
            action=AuditAction.CREATE,
            entity_type="customer",
            entity_id=customer_id,
            actor_id=actor_id,
            details={
                "screen": "adverse_media",
                "result": "hit",
                "hits": len(hits),
                "risk": risk,
                "marble_case_id": marble_case_id,
                "hitl_case_id": hitl_case_id,
                "subjects": [h.article.subject_name for h in hits],
            },
            source=SourceSystem.API,
        )
        return AdverseMediaResult(
            customer_id=customer_id,
            screened_at=now,
            action=ScreeningAction.HITL_REVIEW,
            risk=risk,
            hits=hits,
            marble_case_id=marble_case_id,
            hitl_case_id=hitl_case_id,
        )

    def _open_case(
        self, profile: CustomerProfile, hits: list[AdverseMediaHit], risk: str
    ) -> str | None:
        priority = CasePriority.CRITICAL if risk == "HIGH" else CasePriority.HIGH
        top_score = max(h.composite_score for h in hits)
        request = CaseRequest(
            case_reference=f"AM-{profile.customer_id}",
            case_type=CaseType.EDD,
            entity_id=profile.customer_id,
            entity_type=profile.entity_type.value.lower(),
            priority=priority,
            description=(
                f"Adverse-media hit ({len(hits)}) for {profile.display_name} — "
                "EDD / MLRO review required (MLR 2017 Reg.28)."
            ),
            risk_score=int(top_score),
            metadata={
                "screen": "adverse_media",
                "subjects": [h.article.subject_name for h in hits],
            },
        )
        try:
            return self._case_opener.create_case(request).case_id
        except (OSError, RuntimeError) as exc:  # Marble env not configured — HITL still gates
            logger.error("Marble case open failed (degraded); MLRO HITL still enforced: %s", exc)
            return None

    def _enqueue_mlro(self, profile: CustomerProfile, hits: list[AdverseMediaHit]) -> str:
        subjects = ", ".join(h.article.subject_name for h in hits)
        case = self._hitl.enqueue(
            transaction_id=f"adverse-media:{profile.customer_id}",
            customer_id=profile.customer_id,
            entity_type=profile.entity_type.value.lower(),
            amount=Decimal("0"),
            currency="GBP",
            reasons=[ReviewReason.EDD_REQUIRED],
            fraud_score=0,
            fraud_risk="N/A",
            aml_flags=[f"ADVERSE_MEDIA:{subjects}"],
            hold_reasons=["Adverse-media hit — mandatory MLRO review (no auto-clear)"],
        )
        return case.case_id


def _max_risk(hits: list[AdverseMediaHit]) -> str:
    risks = [_CONFIDENCE_RISK[h.confidence] for h in hits]
    return max(risks, key=lambda r: _RISK_ORDER[r])
