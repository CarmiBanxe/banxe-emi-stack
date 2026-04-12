"""
api/routers/statements.py — Account statement endpoints
FCA PS7/24 | CASS 15 | banxe-emi-stack

GET /v1/accounts/{account_id}/statement      — JSON statement (mobile polling)
GET /v1/accounts/{account_id}/statement/csv  — CSV download (mobile save)

FCA obligations:
  - FCA PS7/24: client statement must be available on request
  - CASS 15: client money statement details required
  - UK GDPR Art.5: only data necessary for the period (I-09)
  - Amounts as Decimal strings (I-05 — never float)
"""

from __future__ import annotations

from datetime import date
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from api.deps import get_statement_service
from api.models.statements import StatementResponse, TransactionLineResponse
from services.statements.statement_service import AccountStatementService

logger = logging.getLogger("banxe.api.statements")

router = APIRouter(tags=["Statements"])


def _to_response(stmt) -> StatementResponse:
    """Convert AccountStatement domain object → StatementResponse."""
    tx_lines = [
        TransactionLineResponse(
            date=tx.date.isoformat(),
            description=tx.description,
            reference=tx.reference,
            debit=str(tx.debit) if tx.debit is not None else None,
            credit=str(tx.credit) if tx.credit is not None else None,
            balance_after=str(tx.balance_after),
            transaction_id=tx.transaction_id,
        )
        for tx in stmt.transactions
    ]
    return StatementResponse(
        statement_id=stmt.statement_id,
        customer_id=stmt.customer_id,
        account_id=stmt.account_id,
        currency=stmt.currency,
        period_start=stmt.period_start.isoformat(),
        period_end=stmt.period_end.isoformat(),
        opening_balance=str(stmt.opening_balance),
        closing_balance=str(stmt.closing_balance),
        total_debits=str(stmt.total_debits),
        total_credits=str(stmt.total_credits),
        net_movement=str(stmt.net_movement),
        transaction_count=stmt.transaction_count,
        transactions=tx_lines,
        generated_at=stmt.generated_at.isoformat(),
    )


@router.get(
    "/accounts/{account_id}/statement",
    response_model=StatementResponse,
    summary="Get account statement (JSON)",
    description=(
        "Returns account statement as JSON for the requested period. "
        "FCA PS7/24: available on customer request. "
        "All amounts are Decimal strings (never float)."
    ),
)
def get_statement(
    account_id: str,
    customer_id: str = Query(..., description="Customer ID owning the account"),
    currency: str = Query("GBP", description="Account currency (ISO 4217)"),
    from_date: date = Query(..., alias="from", description="Period start (YYYY-MM-DD)"),
    to_date: date = Query(..., alias="to", description="Period end (YYYY-MM-DD)"),
    svc: AccountStatementService = Depends(get_statement_service),
) -> StatementResponse:
    """
    GET /v1/accounts/{account_id}/statement?from=2026-03-01&to=2026-03-31&customer_id=cust-001

    Mobile MVP endpoint. Returns JSON — use /csv for downloadable format.
    Period max: 366 days (FCA PS7/24 — one year lookback).
    """
    if to_date < from_date:
        raise HTTPException(
            status_code=422,
            detail="'to' date must be >= 'from' date",
        )
    if (to_date - from_date).days > 366:
        raise HTTPException(
            status_code=422,
            detail="Period must not exceed 366 days",
        )

    logger.info(
        "Statement requested: account=%s customer=%s period=%s..%s",
        account_id,
        customer_id,
        from_date,
        to_date,
    )

    stmt = svc.generate(
        customer_id=customer_id,
        account_id=account_id,
        currency=currency.upper(),
        period_start=from_date,
        period_end=to_date,
    )
    return _to_response(stmt)


@router.get(
    "/accounts/{account_id}/statement/csv",
    summary="Download account statement (CSV)",
    description=(
        "Returns account statement as a downloadable CSV file. "
        "FCA PS7/24: client statement on request. "
        "Suitable for mobile save-to-files and spreadsheet import."
    ),
    responses={
        200: {
            "content": {"text/csv": {}},
            "description": "CSV statement file",
        }
    },
)
def get_statement_csv(
    account_id: str,
    customer_id: str = Query(..., description="Customer ID owning the account"),
    currency: str = Query("GBP", description="Account currency (ISO 4217)"),
    from_date: date = Query(..., alias="from", description="Period start (YYYY-MM-DD)"),
    to_date: date = Query(..., alias="to", description="Period end (YYYY-MM-DD)"),
    svc: AccountStatementService = Depends(get_statement_service),
) -> Response:
    """
    GET /v1/accounts/{account_id}/statement/csv?from=2026-03-01&to=2026-03-31&customer_id=cust-001

    Returns CSV with Content-Disposition: attachment for mobile download.
    """
    if to_date < from_date:
        raise HTTPException(
            status_code=422,
            detail="'to' date must be >= 'from' date",
        )
    if (to_date - from_date).days > 366:
        raise HTTPException(
            status_code=422,
            detail="Period must not exceed 366 days",
        )

    stmt = svc.generate(
        customer_id=customer_id,
        account_id=account_id,
        currency=currency.upper(),
        period_start=from_date,
        period_end=to_date,
    )

    filename = f"statement_{account_id}_{from_date.strftime('%Y%m')}.csv"
    csv_bytes = stmt.to_csv()

    logger.info(
        "Statement CSV downloaded: account=%s customer=%s bytes=%d",
        account_id,
        customer_id,
        len(csv_bytes),
    )

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
