"""
services/crypto_aml_graph/models.py — Crypto-AML graph-analytics domain models + ports
GAP-068 | IMPL-2 | banxe-emi-stack

Graph-analytics AML for incoming crypto (ADR-111; extends GAP-021 fraud ML).
Advisory scoring: auto-block ONLY on a sanctions-match, otherwise HIGH/CRITICAL
routes to a MANDATORY MLRO HITL review (no auto-clear).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Protocol


class FlagCategory(str, Enum):
    """Why an address/cluster is flagged. SANCTIONS is the only auto-block trigger."""

    SANCTIONS = "SANCTIONS"  # OFAC SDN / sanctioned address → auto-block
    MIXER = "MIXER"  # tumbler / coinjoin
    DARKNET = "DARKNET"  # darknet market
    SCAM = "SCAM"  # known scam / fraud
    EXCHANGE_HIGH_RISK = "EXCHANGE_HIGH_RISK"  # high-risk / no-KYC VASP


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ScreenAction(str, Enum):
    """Advisory action. BLOCK only on sanctions-match; HIGH/CRITICAL → MLRO HITL."""

    CLEAR = "CLEAR"
    MONITOR = "MONITOR"
    HITL_REVIEW = "HITL_REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class BlacklistFlag:
    source: str  # e.g. "ofac-0xB10C", "usdt-blacklist", "scorechain"
    category: FlagCategory
    severity: int  # 0-100
    detail: str = ""


@dataclass(frozen=True)
class GraphScreenInput:
    """Pre-crediting screen input for an incoming crypto transfer."""

    address: str
    chain: str  # BTC / ETH / USDT / ... (AssetType value)
    tx_value_eur: Decimal | None = None
    tx_inputs: list[str] = field(default_factory=list)  # co-spent inputs (CIOH)


@dataclass(frozen=True)
class GnnFeatures:
    cluster_size: int
    neighbor_count: int
    peel_chain_depth: int
    blacklist_proximity: int  # number of directly-connected flagged addresses


@dataclass(frozen=True)
class CryptoAmlResult:
    address: str
    chain: str
    risk_score: int  # 0-100
    level: RiskLevel
    action: ScreenAction
    flags: list[BlacklistFlag] = field(default_factory=list)
    cluster_size: int = 0
    travel_rule_required: bool = False
    marble_case_id: str | None = None
    hitl_case_id: str | None = None


class GraphStorePort(Protocol):
    """Entity/tx graph backend (Neo4j in prod, in-memory for tests)."""

    def neighbors(self, address: str) -> list[str]: ...

    def tx_count(self, address: str) -> int: ...


class BlacklistFeedPort(Protocol):
    """Ensemble blacklist feed. Implementations MUST NOT hold secrets in code."""

    def check(self, address: str, chain: str) -> list[BlacklistFlag]: ...
