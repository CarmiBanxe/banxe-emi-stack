"""
api/routers/recon.py — Tri-Party Reconciliation API
GAP-010 D-recon | CASS 7.15.17R | CASS 7.15.29R | banxe-emi-stack

Endpoints:
  GET /v1/recon/status   — latest reconciliation status (today)
  GET /v1/recon/report   — full tri-party report for a given date
  GET /v1/recon/history  — reconciliation history (last N days)

FCA compliance:
  - CASS 7.15.17R: daily tri-party reconciliation (rails ↔ ledger ↔ bank)
  - CASS 7.15.29R: discrepancy escalation within 1 business day
  - Amounts always Decimal strings (I-05 — never float)
  - Tolerance: £1.00 default (CEO decision, D-RECON-DESIGN.md Q3)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field
from src.settlement.reconciler_engine import (
    LedgerBalance,
    NullDiscrepancyReporter,
    RailsBalance,
    SafeguardingBalance,
    TriPartyReconciler,
    TriPartyStatus,
)

logger = logging.getLogger("banxe.api.recon")

router = APIRouter(tags=["Reconciliation (CASS 7.15)"])

# ── Sandbox stub ports ─────────────────────────────────────────────────────────


class _StubLedgerPort:
    """Sandbox stub: fixed Midaz GL balance of £100,000."""

    def get_gl_balance(self, settlement_date: date) -> LedgerBalance:
        return LedgerBalance(
            settlement_date=settlement_date,
            total_client_funds_gbp=Decimal("100000.00"),
            total_operational_gbp=Decimal("0.00"),
            source="stub-midaz",
        )


class _StubBankPort:
    """Sandbox stub: fixed safeguarding bank balance of £100,000."""

    def get_closing_balance(self, statement_date: date) -> SafeguardingBalance | None:
        return SafeguardingBalance(
            statement_date=statement_date,
            closing_balance_gbp=Decimal("100000.00"),
            available_balance_gbp=Decimal("100000.00"),
            account_iban="GB00BARC20000012345678",
            source_file="stub-camt053.xml",
        )


class _StubRailsPort:
    """Sandbox stub: fixed payment rails net-settled of £100,000 (100 txns)."""

    def get_settled_total(self, settlement_date: date) -> RailsBalance:
        return RailsBalance(
            settlement_date=settlement_date,
            total_settled_gbp=Decimal("100000.00"),
            total_refunded_gbp=Decimal("0.00"),
            transaction_count=100,
            source="stub-hyperswitch",
        )


def _get_reconciler() -> TriPartyReconciler:
    """Return TriPartyReconciler wired to sandbox stubs."""
    return TriPartyReconciler(
        ledger_port=_StubLedgerPort(),
        bank_port=_StubBankPort(),
        rails_port=_StubRailsPort(),
        reporter=NullDiscrepancyReporter(),
    )


# ── Response models ────────────────────────────────────────────────────────────


class ReconLegResponse(BaseModel):
    leg: str = Field(..., description="RAILS_VS_LEDGER | LEDGER_VS_BANK | RAILS_VS_BANK")
    left_gbp: str = Field(..., description="Left-side balance (Decimal string)")
    right_gbp: str = Field(..., description="Right-side balance (Decimal string)")
    difference_gbp: str = Field(..., description="Left minus right (signed Decimal string)")
    tolerance_gbp: str = Field(..., description="Allowed tolerance for MATCHED status")
    status: str = Field(..., description="MATCHED | DISCREPANCY | PENDING")
    note: str = Field("", description="Escalation note if DISCREPANCY")


class ReconStatusResponse(BaseModel):
    settlement_date: str = Field(..., description="Date of this reconciliation run")
    overall_status: str = Field(..., description="MATCHED | DISCREPANCY | PENDING | FATAL")
    is_compliant: bool = Field(..., description="True if overall_status is MATCHED")
    rails_net_gbp: str = Field(..., description="Payment rails net-settled amount")
    midaz_client_funds_gbp: str = Field(..., description="Midaz GL client-funds balance")
    safeguarding_bank_gbp: str | None = Field(None, description="External bank closing balance")
    generated_at: str = Field(..., description="UTC timestamp of this response")


class ReconReportResponse(BaseModel):
    settlement_date: str
    overall_status: str
    is_compliant: bool
    rails_net_gbp: str
    rails_transaction_count: int
    midaz_client_funds_gbp: str
    midaz_operational_gbp: str
    safeguarding_bank_gbp: str | None
    safeguarding_source_file: str | None
    legs: list[ReconLegResponse]
    run_at: str
    generated_at: str


class ReconHistoryEntry(BaseModel):
    settlement_date: str
    overall_status: str
    is_compliant: bool
    midaz_client_funds_gbp: str
    safeguarding_bank_gbp: str | None


class ReconHistoryResponse(BaseModel):
    days_requested: int
    entries: list[ReconHistoryEntry]
    generated_at: str


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get(
    "/recon/status",
    response_model=ReconStatusResponse,
    summary="Latest reconciliation status",
    description=(
        "Returns the tri-party reconciliation status for today (or a given date). "
        "CASS 7.15.17R daily reconciliation obligation."
    ),
)
def get_recon_status(
    as_of: Annotated[
        str | None,
        Query(description="ISO date (default: today)", examples=["2026-04-13"]),
    ] = None,
) -> ReconStatusResponse:
    try:
        target_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid date: {as_of}"
        )
    reconciler = _get_reconciler()
    result = reconciler.reconcile(target_date)

    bank_gbp = str(result.safeguarding.closing_balance_gbp) if result.safeguarding else None

    return ReconStatusResponse(
        settlement_date=target_date.isoformat(),
        overall_status=result.overall_status.value,
        is_compliant=result.overall_status == TriPartyStatus.MATCHED,
        rails_net_gbp=str(result.rails.net_settled_gbp),
        midaz_client_funds_gbp=str(result.ledger.total_client_funds_gbp),
        safeguarding_bank_gbp=bank_gbp,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/recon/report",
    response_model=ReconReportResponse,
    summary="Full tri-party reconciliation report",
    description=(
        "Returns a full three-leg reconciliation report for a given date. "
        "Includes per-leg diff, tolerance, and escalation notes."
    ),
)
def get_recon_report(
    as_of: Annotated[
        str | None,
        Query(description="ISO date (default: today)", examples=["2026-04-13"]),
    ] = None,
) -> ReconReportResponse:
    try:
        target_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid date: {as_of}"
        )
    reconciler = _get_reconciler()
    result = reconciler.reconcile(target_date)

    bank_gbp = str(result.safeguarding.closing_balance_gbp) if result.safeguarding else None
    bank_file = result.safeguarding.source_file if result.safeguarding else None

    legs = [
        ReconLegResponse(
            leg=leg.leg.value,
            left_gbp=str(leg.left_gbp),
            right_gbp=str(leg.right_gbp),
            difference_gbp=str(leg.difference_gbp),
            tolerance_gbp=str(leg.tolerance_gbp),
            status=leg.status,
            note=leg.note,
        )
        for leg in result.legs
    ]

    return ReconReportResponse(
        settlement_date=target_date.isoformat(),
        overall_status=result.overall_status.value,
        is_compliant=result.overall_status == TriPartyStatus.MATCHED,
        rails_net_gbp=str(result.rails.net_settled_gbp),
        rails_transaction_count=result.rails.transaction_count,
        midaz_client_funds_gbp=str(result.ledger.total_client_funds_gbp),
        midaz_operational_gbp=str(result.ledger.total_operational_gbp),
        safeguarding_bank_gbp=bank_gbp,
        safeguarding_source_file=bank_file,
        legs=legs,
        run_at=result.run_at.isoformat(),
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/recon/history",
    response_model=ReconHistoryResponse,
    summary="Reconciliation history",
    description=(
        "Returns reconciliation status for the last N days. "
        "Sandbox: all entries are MATCHED with stub balances."
    ),
)
def get_recon_history(
    days: Annotated[
        int,
        Query(ge=1, le=90, description="Number of past days to include (max 90)"),
    ] = 7,
) -> ReconHistoryResponse:
    from datetime import timedelta

    reconciler = _get_reconciler()
    today = date.today()
    entries: list[ReconHistoryEntry] = []

    for offset in range(days):
        target_date = today - timedelta(days=offset)
        result = reconciler.reconcile(target_date)
        bank_gbp = str(result.safeguarding.closing_balance_gbp) if result.safeguarding else None
        entries.append(
            ReconHistoryEntry(
                settlement_date=target_date.isoformat(),
                overall_status=result.overall_status.value,
                is_compliant=result.overall_status == TriPartyStatus.MATCHED,
                midaz_client_funds_gbp=str(result.ledger.total_client_funds_gbp),
                safeguarding_bank_gbp=bank_gbp,
            )
        )

    return ReconHistoryResponse(
        days_requested=days,
        entries=entries,
        generated_at=datetime.now(UTC).isoformat(),
    )
