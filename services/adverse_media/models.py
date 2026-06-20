"""
services/adverse_media/models.py — Adverse-media screening domain models + ports
GAP-064 | IMPL-1 | banxe-emi-stack

MLR 2017 Reg.28(3) | FCA SYSC 6.3 | Banxe I-04.
Advisory output only — an adverse hit ALWAYS routes to MLRO HITL review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from services.case_management.case_port import CaseRequest, CaseResult
from services.sanctions_screening.models import MatchConfidence


class ScreeningAction(str, Enum):
    """Advisory action — never auto-blocks (MLRO decides)."""

    CLEAR = "CLEAR"  # no adverse-media hit
    HITL_REVIEW = "HITL_REVIEW"  # hit → mandatory MLRO review (no auto-clear)


@dataclass(frozen=True)
class AdverseMediaArticle:
    """A single negative-news / adverse-media record about a subject."""

    article_id: str
    subject_name: str
    headline: str
    source: str
    categories: list[str] = field(default_factory=list)  # e.g. ["fraud", "sanctions"]
    subject_dob: str | None = None  # ISO YYYY-MM-DD if known
    subject_jurisdiction: str | None = None  # ISO-3166-1 alpha-2 if known
    url: str | None = None
    published: str | None = None  # ISO date
    snippet: str | None = None


@dataclass(frozen=True)
class AdverseMediaHit:
    """A customer↔article match at/above the configured fuzzy threshold."""

    article: AdverseMediaArticle
    name_score: Decimal
    dob_match: bool
    nat_match: bool
    composite_score: Decimal
    confidence: MatchConfidence


@dataclass(frozen=True)
class AdverseMediaResult:
    """Outcome of a single adverse-media screen."""

    customer_id: str
    screened_at: datetime
    action: ScreeningAction
    risk: str  # NONE / LOW / MEDIUM / HIGH
    hits: list[AdverseMediaHit] = field(default_factory=list)
    marble_case_id: str | None = None
    hitl_case_id: str | None = None


class NegativeNewsFeed(Protocol):
    """Pluggable adverse-media source. Implementations MUST NOT hold secrets in code."""

    def fetch(self, name: str, *, jurisdiction: str | None = None) -> list[AdverseMediaArticle]: ...


class CaseOpenerPort(Protocol):
    """Marble case opener — reuses services.case_management."""

    def create_case(self, request: CaseRequest) -> CaseResult: ...
