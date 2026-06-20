"""
tests/test_crypto_aml_graph.py — IMPL-2 crypto-AML graph analytics (GAP-068)

CIOH clustering, GraphSAGE fallback, ensemble blacklist, service CLEAR/HIT,
sanctions auto-BLOCK, and the MANDATORY MLRO HITL gate (no auto-clear).
Reuses real EventStore / HITLService (in-memory); fakes for graph + Marble.
"""

from __future__ import annotations

from decimal import Decimal

from services.audit_trail.event_store import EventStore
from services.case_management.case_port import CaseRequest, CaseResult, CaseStatus
from services.crypto_aml_graph.blacklist_feed import EnsembleBlacklistFeed
from services.crypto_aml_graph.clustering import CIOHClusterer
from services.crypto_aml_graph.gnn_inference import GraphSageInference
from services.crypto_aml_graph.models import (
    BlacklistFlag,
    FlagCategory,
    GnnFeatures,
    GraphScreenInput,
    RiskLevel,
    ScreenAction,
)
from services.crypto_aml_graph.neo4j_adapter import InMemoryGraphStore
from services.crypto_aml_graph.service import CryptoAmlGraphService
from services.hitl.hitl_port import CaseStatus as HITLCaseStatus
from services.hitl.hitl_service import HITLService

_SANCTIONED = "1OFACbadaddress"


class _FakeOpener:
    def __init__(self) -> None:
        self.requests: list[CaseRequest] = []

    def create_case(self, request: CaseRequest) -> CaseResult:
        self.requests.append(request)
        from datetime import UTC, datetime

        return CaseResult(
            case_id="marble-caml-1",
            case_reference=request.case_reference,
            status=CaseStatus.OPEN,
            provider="mock",
            created_at=datetime(2026, 6, 20, tzinfo=UTC),
        )


def _service(
    blacklist: EnsembleBlacklistFeed,
    graph: InMemoryGraphStore | None = None,
    opener: _FakeOpener | None = None,
    audit: EventStore | None = None,
    hitl: HITLService | None = None,
) -> CryptoAmlGraphService:
    return CryptoAmlGraphService(
        graph_store=graph or InMemoryGraphStore(),
        blacklist=blacklist,
        case_opener=opener or _FakeOpener(),
        audit=audit or EventStore(),
        hitl=hitl or HITLService(),
    )


def _empty_feed() -> EnsembleBlacklistFeed:
    return EnsembleBlacklistFeed(static_blacklist={}, adapters=[])


def _sanctions_feed() -> EnsembleBlacklistFeed:
    return EnsembleBlacklistFeed(
        static_blacklist={
            _SANCTIONED: [
                BlacklistFlag("ofac-0xB10C", FlagCategory.SANCTIONS, 100, "OFAC SDN"),
            ]
        },
        adapters=[],
    )


class TestClustering:
    def test_cioh_unions_inputs_and_seed(self) -> None:
        cluster = CIOHClusterer().cluster(["a", "b", "a"], seed="c")
        assert cluster == frozenset({"a", "b", "c"})

    def test_cluster_risk_saturates(self) -> None:
        assert CIOHClusterer().cluster_risk_score(1) == Decimal("0")
        assert CIOHClusterer().cluster_risk_score(100) == Decimal("100")


class TestGnnFallback:
    def test_clean_features_low_score(self) -> None:
        score = GraphSageInference().score(
            GnnFeatures(cluster_size=0, neighbor_count=0, peel_chain_depth=0, blacklist_proximity=0)
        )
        assert score == Decimal("0")

    def test_blacklist_proximity_drives_high_score(self) -> None:
        score = GraphSageInference().score(
            GnnFeatures(cluster_size=2, neighbor_count=3, peel_chain_depth=1, blacklist_proximity=2)
        )
        assert score >= Decimal("65")


class TestBlacklist:
    def test_empty_feed_no_secrets_no_flags(self) -> None:
        assert _empty_feed().check("anyaddr", "BTC") == []

    def test_static_sanctions_flag(self) -> None:
        flags = _sanctions_feed().check(_SANCTIONED, "BTC")
        assert len(flags) == 1
        assert flags[0].category is FlagCategory.SANCTIONS


class TestService:
    def test_clear_when_clean(self) -> None:
        res = _service(_empty_feed()).screen(GraphScreenInput(address="cleanaddr", chain="BTC"))
        assert res.action is ScreenAction.CLEAR
        assert res.level is RiskLevel.LOW
        assert res.hitl_case_id is None

    def test_sanctions_match_auto_blocks(self) -> None:
        opener = _FakeOpener()
        res = _service(_sanctions_feed(), opener=opener).screen(
            GraphScreenInput(address=_SANCTIONED, chain="BTC")
        )
        assert res.action is ScreenAction.BLOCK
        assert res.level is RiskLevel.CRITICAL
        assert res.risk_score == 100
        assert res.marble_case_id == "marble-caml-1"

    def test_travel_rule_flagged_above_threshold(self) -> None:
        res = _service(_empty_feed()).screen(
            GraphScreenInput(address="x", chain="ETH", tx_value_eur=Decimal("5000"))
        )
        assert res.travel_rule_required is True

    def test_hit_appends_audit(self) -> None:
        audit = EventStore()
        _service(_sanctions_feed(), audit=audit).screen(
            GraphScreenInput(address=_SANCTIONED, chain="BTC")
        )
        events = audit.list_by_entity(_SANCTIONED)
        assert any(e.details.get("action") == "BLOCK" for e in events)


class TestHITLGate:
    def test_sanctions_hit_enqueues_mlro_no_auto_clear(self) -> None:
        hitl = HITLService()
        res = _service(_sanctions_feed(), hitl=hitl).screen(
            GraphScreenInput(address=_SANCTIONED, chain="BTC")
        )
        assert res.hitl_case_id is not None
        case = hitl.get_case(res.hitl_case_id)
        assert case is not None
        assert case.status is HITLCaseStatus.PENDING  # mandatory review, not auto-cleared
