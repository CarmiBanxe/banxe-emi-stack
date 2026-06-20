"""
api/routers/crypto_aml_graph.py — Crypto-AML graph screening endpoint
GAP-068 | IMPL-2 | banxe-emi-stack

POST /v1/compliance/crypto-aml/screen {address, chain, tx} -> {risk_score, level, flags[], action}
ADR-111. Advisory scoring — auto-block only on sanctions-match; HIGH/CRITICAL → MLRO HITL.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from fastapi import APIRouter

from api.models.crypto_aml_graph import FlagModel, ScreenRequest, ScreenResponse
from services.crypto_aml_graph.models import GraphScreenInput
from services.crypto_aml_graph.service import CryptoAmlGraphService

router = APIRouter(tags=["Crypto-AML Graph Screening"])


@lru_cache(maxsize=1)
def _get_service() -> CryptoAmlGraphService:
    return CryptoAmlGraphService()


@router.post("/compliance/crypto-aml/screen", response_model=ScreenResponse)
def screen(req: ScreenRequest) -> ScreenResponse:
    inp = GraphScreenInput(
        address=req.address,
        chain=req.chain,
        tx_value_eur=Decimal(str(req.tx_value_eur)) if req.tx_value_eur is not None else None,
        tx_inputs=req.tx_inputs,
    )
    result = _get_service().screen(inp)
    return ScreenResponse(
        address=result.address,
        chain=result.chain,
        risk_score=result.risk_score,
        level=result.level.value,
        action=result.action.value,
        flags=[
            FlagModel(
                source=f.source,
                category=f.category.value,
                severity=f.severity,
                detail=f.detail,
            )
            for f in result.flags
        ],
        cluster_size=result.cluster_size,
        travel_rule_required=result.travel_rule_required,
        marble_case_id=result.marble_case_id,
        hitl_case_id=result.hitl_case_id,
    )
