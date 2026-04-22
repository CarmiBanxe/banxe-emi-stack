"""
api/routers/compliance_sync.py — Compliance Matrix Auto-Sync endpoints
IL-CMS-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from services.compliance_sync.matrix_scanner import MatrixScanner

logger = logging.getLogger("banxe.compliance_sync")
router = APIRouter(tags=["ComplianceMatrix"])

_scanner = MatrixScanner()


@router.get("/compliance-matrix/scan", summary="Trigger full compliance matrix scan")
async def scan_compliance_matrix():
    report = _scanner.scan_all()
    return {
        "scanned_at": report.scanned_at,
        "coverage_pct": report.coverage_pct,
        "done_count": report.done_count,
        "not_started_count": report.not_started_count,
        "blocked_count": report.blocked_count,
        "total": len(report.entries),
        "entries": [
            {
                "block": e.block,
                "item_id": e.item_id,
                "description": e.description,
                "status": e.status.value,
                "actual_path": e.actual_path,
            }
            for e in report.entries
        ],
    }


@router.get("/compliance-matrix/report", summary="Latest compliance matrix report")
async def get_compliance_report():
    if not _scanner.scan_log:
        report = _scanner.scan_all()
    else:
        report = _scanner.scan_log[-1]
    return {
        "scanned_at": report.scanned_at,
        "coverage_pct": report.coverage_pct,
        "done_count": report.done_count,
        "not_started_count": report.not_started_count,
        "entries": [e.model_dump() for e in report.entries],
    }


@router.get("/compliance-matrix/gaps", summary="NOT_STARTED and BLOCKED items only")
async def get_compliance_gaps():
    gaps = _scanner.get_gaps()
    return {
        "gap_count": len(gaps),
        "gaps": [
            {
                "block": e.block,
                "item_id": e.item_id,
                "description": e.description,
                "status": e.status.value,
                "expected_artifact": e.expected_artifact,
            }
            for e in gaps
        ],
    }
