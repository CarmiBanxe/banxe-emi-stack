"""
services/crypto_aml_graph/service.py — CryptoAmlGraphService orchestration
GAP-068 | IMPL-2 | banxe-emi-stack

Pre-crediting AML screen for incoming crypto (ADR-111; extends GAP-021 fraud ML).
Orchestrates CIOH clustering + GraphSAGE inference + ensemble blacklist into a
risk score / level. On a sanctions-match → auto-BLOCK; on HIGH/CRITICAL (non-
sanctions) → MANDATORY MLRO HITL (no auto-clear). Every hit opens a Marble case
and appends an append-only ClickHouse audit event. Travel Rule (ADR-114) flagged.
Reuses case_management / audit_trail / hitl — no structured-screening reimplementation.
"""

from __future__ import annotations

from decimal import Decimal
import logging

from services.audit_trail.event_store import EventStore
from services.audit_trail.models import (
    AuditAction,
    EventCategory,
    EventSeverity,
    SourceSystem,
)
from services.case_management.case_port import CasePriority, CaseRequest, CaseResult, CaseType
from services.crypto_aml_graph.blacklist_feed import EnsembleBlacklistFeed
from services.crypto_aml_graph.clustering import CIOHClusterer
from services.crypto_aml_graph.gnn_inference import GraphSageInference
from services.crypto_aml_graph.models import (
    BlacklistFeedPort,
    BlacklistFlag,
    CryptoAmlResult,
    FlagCategory,
    GnnFeatures,
    GraphScreenInput,
    GraphStorePort,
    RiskLevel,
    ScreenAction,
)
from services.crypto_aml_graph.neo4j_adapter import InMemoryGraphStore
from services.crypto_custody.travel_rule_engine import TravelRuleEngine
from services.hitl.hitl_port import ReviewReason
from services.hitl.hitl_service import HITLService

logger = logging.getLogger(__name__)

_CRITICAL_SCORE = 85
_HIGH_SCORE = 65
_MEDIUM_SCORE = 40


class _LazyMarbleOpener:
    """Default case opener — instantiates MarbleAdapter lazily (needs env at call time)."""

    def create_case(self, request: CaseRequest) -> CaseResult:
        from services.case_management.marble_adapter import MarbleAdapter

        return MarbleAdapter().create_case(request)


class CryptoAmlGraphService:
    """Graph-analytics AML screen for incoming crypto transfers."""

    def __init__(
        self,
        *,
        graph_store: GraphStorePort | None = None,
        blacklist: BlacklistFeedPort | None = None,
        clusterer: CIOHClusterer | None = None,
        gnn: GraphSageInference | None = None,
        travel_rule: TravelRuleEngine | None = None,
        case_opener: object | None = None,
        audit: EventStore | None = None,
        hitl: HITLService | None = None,
    ) -> None:
        self._graph: GraphStorePort = graph_store or InMemoryGraphStore()
        self._blacklist: BlacklistFeedPort = blacklist or EnsembleBlacklistFeed()
        self._clusterer = clusterer or CIOHClusterer()
        self._gnn = gnn or GraphSageInference()
        self._travel_rule = travel_rule or TravelRuleEngine()
        self._case_opener = case_opener or _LazyMarbleOpener()
        self._audit = audit or EventStore()
        self._hitl = hitl or HITLService()

    def screen(self, inp: GraphScreenInput, *, actor_id: str = "system") -> CryptoAmlResult:
        flags = self._blacklist.check(inp.address, inp.chain)
        cluster = self._clusterer.cluster(inp.tx_inputs, seed=inp.address)
        neighbors = self._graph.neighbors(inp.address)
        proximity = sum(1 for n in neighbors if self._blacklist.check(n, inp.chain))
        features = GnnFeatures(
            cluster_size=len(cluster),
            neighbor_count=len(neighbors),
            peel_chain_depth=self._peel_depth(neighbors),
            blacklist_proximity=proximity,
        )
        sanctions = any(f.category is FlagCategory.SANCTIONS for f in flags)
        gnn_score = self._gnn.score(features)
        risk_score = 100 if sanctions else int(min(Decimal("100"), max(gnn_score, _max_sev(flags))))
        level = _level(risk_score, sanctions=sanctions)
        action = _action(level, sanctions=sanctions)
        travel_rule_required = (
            inp.tx_value_eur is not None
            and self._travel_rule.requires_travel_rule(inp.tx_value_eur)
        )

        marble_case_id: str | None = None
        hitl_case_id: str | None = None
        if action in (ScreenAction.HITL_REVIEW, ScreenAction.BLOCK):
            marble_case_id = self._open_case(inp, risk_score, level, flags)
            hitl_case_id = self._enqueue_mlro(inp, level, flags)

        self._audit_screen(inp, risk_score, level, action, flags, actor_id)
        return CryptoAmlResult(
            address=inp.address,
            chain=inp.chain,
            risk_score=risk_score,
            level=level,
            action=action,
            flags=flags,
            cluster_size=len(cluster),
            travel_rule_required=travel_rule_required,
            marble_case_id=marble_case_id,
            hitl_case_id=hitl_case_id,
        )

    @staticmethod
    def _peel_depth(neighbors: list[str]) -> int:
        # Single-successor hops approximate a peel chain; bounded by neighbour count.
        return 1 if len(neighbors) == 1 else 0

    def _open_case(
        self, inp: GraphScreenInput, risk_score: int, level: RiskLevel, flags: list[BlacklistFlag]
    ) -> str | None:
        priority = CasePriority.CRITICAL if level is RiskLevel.CRITICAL else CasePriority.HIGH
        request = CaseRequest(
            case_reference=f"CAML-{inp.chain}-{inp.address}",
            case_type=CaseType.FRAUD_REVIEW,
            entity_id=inp.address,
            entity_type="crypto_address",
            priority=priority,
            description=(
                f"Crypto-AML graph hit ({level.value}) on {inp.chain}:{inp.address} — "
                "MLRO review required (ADR-111)."
            ),
            risk_score=risk_score,
            metadata={"chain": inp.chain, "flags": [f.source for f in flags]},
        )
        try:
            return self._case_opener.create_case(request).case_id
        except (OSError, RuntimeError) as exc:  # Marble env not configured — HITL still gates
            logger.error("Marble case open failed (degraded); MLRO HITL still enforced: %s", exc)
            return None

    def _enqueue_mlro(
        self, inp: GraphScreenInput, level: RiskLevel, flags: list[BlacklistFlag]
    ) -> str:
        case = self._hitl.enqueue(
            transaction_id=f"crypto-aml:{inp.chain}:{inp.address}",
            customer_id=inp.address,
            entity_type="crypto_address",
            amount=inp.tx_value_eur or Decimal("0"),
            currency="EUR",
            reasons=[ReviewReason.AML_COMBINED],
            fraud_score=0,
            fraud_risk=level.value,
            aml_flags=[f"{f.category.value}:{f.source}" for f in flags],
            hold_reasons=[f"Crypto-AML {level.value} — mandatory MLRO review (no auto-clear)"],
        )
        return case.case_id

    def _audit_screen(
        self,
        inp: GraphScreenInput,
        risk_score: int,
        level: RiskLevel,
        action: ScreenAction,
        flags: list[BlacklistFlag],
        actor_id: str,
    ) -> None:
        hit = action in (ScreenAction.HITL_REVIEW, ScreenAction.BLOCK)
        self._audit.append(
            category=EventCategory.AML,
            severity=EventSeverity.WARNING if hit else EventSeverity.INFO,
            action=AuditAction.CREATE if hit else AuditAction.READ,
            entity_type="crypto_address",
            entity_id=inp.address,
            actor_id=actor_id,
            details={
                "screen": "crypto_aml_graph",
                "chain": inp.chain,
                "risk_score": risk_score,
                "level": level.value,
                "action": action.value,
                "flags": [f"{f.category.value}:{f.source}" for f in flags],
            },
            source=SourceSystem.API,
        )


def _max_sev(flags: list[BlacklistFlag]) -> Decimal:
    return Decimal(max((f.severity for f in flags), default=0))


def _level(risk_score: int, *, sanctions: bool) -> RiskLevel:
    if sanctions or risk_score >= _CRITICAL_SCORE:
        return RiskLevel.CRITICAL
    if risk_score >= _HIGH_SCORE:
        return RiskLevel.HIGH
    if risk_score >= _MEDIUM_SCORE:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _action(level: RiskLevel, *, sanctions: bool) -> ScreenAction:
    if sanctions:
        return ScreenAction.BLOCK
    if level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
        return ScreenAction.HITL_REVIEW
    if level is RiskLevel.MEDIUM:
        return ScreenAction.MONITOR
    return ScreenAction.CLEAR
