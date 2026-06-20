"""
api/models/crypto_aml_graph.py — Crypto-AML graph screening API DTOs
GAP-068 | IMPL-2 | banxe-emi-stack
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ScreenRequest(BaseModel):
    address: str = Field(..., description="Crypto address to screen")
    chain: str = Field(..., description="Chain / asset (BTC, ETH, USDT, ...)")
    tx_value_eur: float | None = Field(default=None, description="Incoming tx value in EUR")
    tx_inputs: list[str] = Field(default_factory=list, description="Co-spent input addresses")


class FlagModel(BaseModel):
    source: str
    category: str
    severity: int
    detail: str


class ScreenResponse(BaseModel):
    address: str
    chain: str
    risk_score: int
    level: str  # LOW | MEDIUM | HIGH | CRITICAL
    action: str  # CLEAR | MONITOR | HITL_REVIEW | BLOCK
    flags: list[FlagModel]
    cluster_size: int
    travel_rule_required: bool
    marble_case_id: str | None = None
    hitl_case_id: str | None = None
