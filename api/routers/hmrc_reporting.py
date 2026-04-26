"""
api/routers/hmrc_reporting.py -- HMRC FATCA/CRS Reporting endpoints
IL-HMR-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.fatca_crs.hmrc_reporter import HMRCReporter

logger = logging.getLogger("banxe.hmrc")
router = APIRouter(tags=["HMRCReporting"])

_reporter = HMRCReporter()


class GenerateRequest(BaseModel):
    tax_year: int
    accounts: list[dict] = []


@router.post("/hmrc/reports/generate", summary="Generate HMRC annual report (I-27 HITL L4)")
async def generate_hmrc_report(body: GenerateRequest):
    result = _reporter.generate_annual_report(body.tax_year, body.accounts)
    from services.fatca_crs.hmrc_reporter import HMRCHITLProposal

    if isinstance(result, HMRCHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "requires_approval_from": result.requires_approval_from,
            "approved": result.approved,
        }
    return {"report_id": result.report_id, "status": result.status}


@router.get("/hmrc/reports/{tax_year}", summary="Get HMRC report for tax year")
async def get_hmrc_report(tax_year: int):
    report = _reporter._store.get_by_year(tax_year)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for tax year {tax_year}")
    return {
        "report_id": report.report_id,
        "tax_year": report.tax_year,
        "total_accounts": report.total_accounts,
        "status": report.status,
        "generated_at": report.generated_at,
    }


@router.post("/hmrc/reports/{tax_year}/validate", summary="Validate HMRC report against XSD")
async def validate_hmrc_report(tax_year: int):
    report = _reporter._store.get_by_year(tax_year)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No report found for tax year {tax_year}")
    result = _reporter.validate_report(report)
    return {
        "report_id": result.report_id,
        "valid": result.valid,
        "error_count": len(result.errors),
        "errors": [{"field": e.field, "message": e.message} for e in result.errors],
    }
