"""
api/routers/safeguarding.py — CASS 15 Safeguarding API
CASS 7.15.17R | CASS 7.15.29R | CASS 15.12.4R | PS23/3 | banxe-emi-stack

Endpoints:
  GET  /v1/safeguarding/position         — daily client funds position
  GET  /v1/safeguarding/accounts         — safeguarding account list
  GET  /v1/safeguarding/breaches         — breach history log
  POST /v1/safeguarding/reconcile        — trigger daily reconciliation
  GET  /v1/safeguarding/resolution-pack  — export resolution pack
  POST /v1/safeguarding/fca-return       — generate monthly FCA safeguarding return

FCA compliance:
  - CASS 7.15.17R: daily internal reconciliation mandatory
  - CASS 7.15.29R: breach alert within 1 business day
  - CASS 15.12.4R: monthly FIN060 return to FCA
  - All amounts Decimal strings (I-05 — never float)
  - All responses logged with X-Request-ID (I-24 audit trail)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from src.safeguarding.agent import (
    InMemoryStreakCounter,
    SafeguardingAgent,
    SafeguardingAgentPorts,
    StubBankStatementPort,
    StubLedgerPort,
)
from src.safeguarding.audit_trail import AuditTrail
from src.safeguarding.daily_reconciliation import DailyReconciliation
from src.safeguarding.fin060_generator import FIN060Generator

logger = logging.getLogger("banxe.api.safeguarding")

router = APIRouter(tags=["Safeguarding (CASS 15)"])

# ── Dependency helpers ─────────────────────────────────────────────────────────


def get_safeguarding_agent() -> SafeguardingAgent:
    """Return SafeguardingAgent wired to sandbox stubs.

    Production: replace stubs with real Midaz + Barclays adapters.
    """
    ports = SafeguardingAgentPorts(
        ledger=StubLedgerPort(balance_gbp=Decimal("100000.00")),
        bank=StubBankStatementPort(balance_gbp=Decimal("100000.00")),
        audit=AuditTrail(clickhouse_url="", dry_run=True),
        streak_counter=InMemoryStreakCounter(),
    )
    return SafeguardingAgent(ports, fca_notify=False)


def get_audit_trail() -> AuditTrail:
    return AuditTrail(clickhouse_url="", dry_run=True)


# ── Response models ────────────────────────────────────────────────────────────


class SafeguardingPositionResponse(BaseModel):
    as_of: str = Field(..., description="Date of position (ISO-8601)")
    total_client_funds_gbp: str = Field(..., description="Internal ledger balance (Decimal string)")
    total_safeguarded_gbp: str = Field(..., description="External bank balance (Decimal string)")
    difference_gbp: str = Field(..., description="Surplus / shortfall (positive = surplus)")
    status: str = Field(..., description="MATCHED | BREAK | PENDING")
    is_compliant: bool = Field(..., description="True if |difference| ≤ £0.01")
    generated_at: str = Field(..., description="UTC timestamp of this response")


class SafeguardingAccountResponse(BaseModel):
    account_id: str
    bank_name: str
    account_number: str
    sort_code: str
    account_type: str
    balance_gbp: str
    last_updated: str
    is_active: bool


class BreachLogEntryResponse(BaseModel):
    breach_date: str
    severity: str
    consecutive_days: int
    shortfall_gbp: str | None
    description: str
    fca_notification_required: bool
    raised_at: str
    resolved: bool


class ReconcileRequest(BaseModel):
    run_date: str | None = Field(
        None,
        description="ISO date to reconcile (default: today)",
        examples=["2026-04-13"],
    )
    dry_run: bool = Field(True, description="If true, write to audit but do not notify FCA")


class ReconcileResponse(BaseModel):
    run_date: str
    status: str
    internal_balance_gbp: str
    external_balance_gbp: str | None
    difference_gbp: str | None
    breach_alert: dict | None
    audit_event_id: str
    exit_code: int


class ResolutionPackResponse(BaseModel):
    generated_at: str
    as_of: str
    client_funds_gbp: str
    safeguarded_gbp: str
    difference_gbp: str
    recon_status: str
    accounts: list[SafeguardingAccountResponse]
    open_breaches: list[BreachLogEntryResponse]
    resolution_deadline_hours: int = Field(
        48, description="CASS 15: resolution pack must be executable within 48h"
    )


class FIN060ReturnRequest(BaseModel):
    year: int = Field(..., ge=2020, le=2030, description="Return year", examples=[2026])
    month: int = Field(..., ge=1, le=12, description="Return month (1-12)", examples=[4])
    firm_name: str = Field("Banxe AI Bank Ltd", description="FCA-registered firm name")
    frn: str = Field("000000", description="FCA Firm Reference Number")


class FIN060ReturnResponse(BaseModel):
    period: str
    firm_name: str
    frn: str
    total_client_money_gbp: str
    total_safeguarded_gbp: str
    shortfall_gbp: str | None
    surplus_gbp: str | None
    is_compliant: bool
    generated_at: str
    csv_row: dict


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.get(
    "/safeguarding/position",
    response_model=SafeguardingPositionResponse,
    summary="Daily safeguarding position",
    description="Returns current client funds vs safeguarded balance. CASS 7.15.17R.",
)
def get_safeguarding_position(
    as_of: Annotated[
        str | None,
        Query(description="ISO date for position (default: today)", examples=["2026-04-13"]),
    ] = None,
) -> SafeguardingPositionResponse:
    try:
        target_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid date: {as_of}"
        )

    # Sandbox: fixed balances — production wires real Midaz + CAMT.053
    internal_balance = Decimal("100000.00")
    external_balance = Decimal("100000.00")

    recon = DailyReconciliation(
        internal_balance_gbp=internal_balance,
        external_balance_gbp=external_balance,
        recon_date=target_date,
    )
    result = recon.run()
    diff = result.difference_gbp or Decimal("0")

    return SafeguardingPositionResponse(
        as_of=target_date.isoformat(),
        total_client_funds_gbp=str(internal_balance),
        total_safeguarded_gbp=str(external_balance),
        difference_gbp=str(diff),
        status=result.status.value,
        is_compliant=result.is_compliant,
        generated_at=datetime.now(UTC).isoformat(),
    )


@router.get(
    "/safeguarding/accounts",
    response_model=list[SafeguardingAccountResponse],
    summary="Safeguarding account list",
    description="Lists all designated safeguarding accounts (CASS 7.13).",
)
def list_safeguarding_accounts() -> list[SafeguardingAccountResponse]:
    # Sandbox: return configured safeguarding accounts
    # Production: fetch from bank integration / config store
    return [
        SafeguardingAccountResponse(
            account_id="safeguarding-barclays-001",
            bank_name="Barclays Bank PLC",
            account_number="12345678",
            sort_code="20-00-00",
            account_type="DESIGNATED_SAFEGUARDING",
            balance_gbp="100000.00",
            last_updated=datetime.now(UTC).isoformat(),
            is_active=True,
        ),
        SafeguardingAccountResponse(
            account_id="safeguarding-hsbc-001",
            bank_name="HSBC UK Bank PLC",
            account_number="87654321",
            sort_code="40-00-00",
            account_type="DESIGNATED_SAFEGUARDING",
            balance_gbp="0.00",
            last_updated=datetime.now(UTC).isoformat(),
            is_active=False,
        ),
    ]


@router.get(
    "/safeguarding/breaches",
    response_model=list[BreachLogEntryResponse],
    summary="Breach history log",
    description="Returns all safeguarding breach events (CASS 7.15.29R).",
)
def list_breaches(
    days: Annotated[
        int,
        Query(ge=1, le=365, description="Number of days of history to return"),
    ] = 30,
    severity: Annotated[
        str | None,
        Query(description="Filter by severity: MINOR | MAJOR | CRITICAL"),
    ] = None,
) -> list[BreachLogEntryResponse]:
    # Sandbox: empty breach log — production reads from ClickHouse audit trail
    logger.info("Fetching breach log: last %d days, severity=%s", days, severity)
    return []


@router.post(
    "/safeguarding/reconcile",
    response_model=ReconcileResponse,
    summary="Trigger daily reconciliation",
    description=(
        "Runs CASS 7.15.17R daily reconciliation and records result to audit trail. "
        "In sandbox: uses stub balances and dry_run=True."
    ),
)
def trigger_reconciliation(
    request: ReconcileRequest,
    agent: Annotated[SafeguardingAgent, Depends(get_safeguarding_agent)],
) -> ReconcileResponse:
    try:
        run_date = date.fromisoformat(request.run_date) if request.run_date else date.today()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid date: {request.run_date}",
        )

    result = agent.run(run_date)

    breach_summary = None
    if result.breach_alert:
        breach_summary = {
            "reference": result.breach_alert.reference,
            "severity": result.breach_alert.severity.value,
            "consecutive_days": result.breach_alert.consecutive_days,
            "fca_notification_required": result.breach_alert.fca_notification_required,
        }

    external_bal = None
    diff = None
    if result.recon_result:
        external_bal = (
            str(result.recon_result.external_balance_gbp)
            if result.recon_result.external_balance_gbp is not None
            else None
        )
        diff = (
            str(result.recon_result.difference_gbp)
            if result.recon_result.difference_gbp is not None
            else None
        )

    return ReconcileResponse(
        run_date=run_date.isoformat(),
        status=result.status_label,
        internal_balance_gbp=str(
            result.recon_result.internal_balance_gbp if result.recon_result else Decimal("0")
        ),
        external_balance_gbp=external_bal,
        difference_gbp=diff,
        breach_alert=breach_summary,
        audit_event_id=result.audit_event_id,
        exit_code=result.exit_code,
    )


@router.get(
    "/safeguarding/resolution-pack",
    response_model=ResolutionPackResponse,
    summary="Export resolution pack",
    description=(
        "Generates a resolution pack — all data needed to distribute client funds "
        "within 48h (CASS 15.12). Required for FCA authorisation."
    ),
)
def get_resolution_pack(
    as_of: Annotated[
        str | None,
        Query(description="ISO date (default: today)"),
    ] = None,
) -> ResolutionPackResponse:
    try:
        target_date = date.fromisoformat(as_of) if as_of else date.today()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid date: {as_of}"
        )

    accounts = list_safeguarding_accounts()
    internal_balance = Decimal("100000.00")
    external_balance = Decimal("100000.00")
    diff = external_balance - internal_balance  # positive = surplus

    recon = DailyReconciliation(
        internal_balance_gbp=internal_balance,
        external_balance_gbp=external_balance,
        recon_date=target_date,
    )
    result = recon.run()

    return ResolutionPackResponse(
        generated_at=datetime.now(UTC).isoformat(),
        as_of=target_date.isoformat(),
        client_funds_gbp=str(internal_balance),
        safeguarded_gbp=str(external_balance),
        difference_gbp=str(diff),
        recon_status=result.status.value,
        accounts=accounts,
        open_breaches=[],
        resolution_deadline_hours=48,
    )


@router.post(
    "/safeguarding/fca-return",
    response_model=FIN060ReturnResponse,
    summary="Generate monthly FCA safeguarding return",
    description="Generates FIN060 monthly return (CASS 15.12.4R).",
)
def generate_fca_return(request: FIN060ReturnRequest) -> FIN060ReturnResponse:
    from datetime import date as _date

    reference_month = _date(request.year, request.month, 1)
    gen = FIN060Generator(
        institution_name=request.firm_name,
        frn=request.frn,
        reference_month=reference_month,
    )
    client_funds = Decimal("100000.00")
    safeguarding_bal = Decimal("100000.00")
    fin060 = gen.build(
        total_client_funds_gbp=client_funds,
        safeguarding_balance_gbp=safeguarding_bal,
        num_safeguarding_accounts=1,
        safeguarding_bank="Barclays Bank PLC",
        daily_recon_count=22,
        daily_recon_breaks=0,
    )

    shortfall = str(fin060.shortfall_gbp) if fin060.shortfall_gbp > Decimal("0") else None
    surplus = str(fin060.surplus_gbp) if fin060.surplus_gbp > Decimal("0") else None

    return FIN060ReturnResponse(
        period=fin060.month_label,
        firm_name=fin060.institution_name,
        frn=fin060.frn,
        total_client_money_gbp=str(fin060.total_client_funds_gbp),
        total_safeguarded_gbp=str(fin060.safeguarding_balance_gbp),
        shortfall_gbp=shortfall,
        surplus_gbp=surplus,
        is_compliant=fin060.is_compliant,
        generated_at=datetime.now(UTC).isoformat(),
        csv_row=fin060.to_dict(),
    )
