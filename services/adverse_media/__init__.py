"""
services/adverse_media — Adverse-media / negative-news screening (GAP-064, IMPL-1).

Enhanced Due Diligence support under MLR 2017 Reg.28(3), FCA SYSC 6.3, Banxe I-04.
Reuses structured screening (sanctions_screening fuzzy matcher), Marble case
management, the append-only ClickHouse audit trail and the MLRO HITL queue —
it does NOT reimplement structured screening. Advisory output only: an adverse
hit ALWAYS routes to MLRO review (no auto-clear, no auto-block).
"""

from __future__ import annotations

from services.adverse_media.matcher import AdverseMediaMatcher
from services.adverse_media.models import (
    AdverseMediaArticle,
    AdverseMediaHit,
    AdverseMediaResult,
    ScreeningAction,
)
from services.adverse_media.service import AdverseMediaService

__all__ = [
    "AdverseMediaArticle",
    "AdverseMediaHit",
    "AdverseMediaMatcher",
    "AdverseMediaResult",
    "AdverseMediaService",
    "ScreeningAction",
]
