"""
api/routers/experiments.py — Compliance Experiment Copilot REST API
IL-CEC-01 | banxe-emi-stack

Endpoints:
  POST   /v1/experiments/design           — design a new experiment (draft)
  GET    /v1/experiments                  — list experiments by status
  GET    /v1/experiments/{id}             — get experiment details
  PATCH  /v1/experiments/{id}/approve     — approve a draft experiment
  PATCH  /v1/experiments/{id}/reject      — reject a draft experiment
  GET    /v1/experiments/metrics/current  — get current AML metrics snapshot
  POST   /v1/experiments/{id}/propose     — propose a change (PR + issue)
  GET    /v1/experiments/{id}/audit       — get audit trail for experiment
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from services.experiment_copilot.agents.change_proposer import (
    ChangeProposer,
    InMemoryGitHubPort,
)
from services.experiment_copilot.agents.experiment_designer import (
    ExperimentDesigner,
    InMemoryKBPort,
)
from services.experiment_copilot.agents.experiment_steward import (
    ExperimentSteward,
    ValidationError,
)
from services.experiment_copilot.agents.metrics_reporter import (
    InMemoryClickHousePort,
    MetricsReporter,
)
from services.experiment_copilot.models.experiment import (
    ApproveRequest,
    ComplianceExperiment,
    DesignRequest,
    ExperimentStatus,
    ExperimentSummary,
    RejectRequest,
)
from services.experiment_copilot.models.proposal import ChangeProposal, ProposeRequest
from services.experiment_copilot.store.audit_trail import AuditEntry, AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore

logger = logging.getLogger("banxe.api.experiments")

router = APIRouter(prefix="/experiments", tags=["experiments"])

# ── Dependency providers ──────────────────────────────────────────────────


def get_store() -> ExperimentStore:
    return ExperimentStore()


def get_audit() -> AuditTrail:
    return AuditTrail()


def get_designer(
    store: ExperimentStore = Depends(get_store),
    audit: AuditTrail = Depends(get_audit),
) -> ExperimentDesigner:
    return ExperimentDesigner(store=store, audit=audit, kb_port=InMemoryKBPort())


def get_steward(
    store: ExperimentStore = Depends(get_store),
    audit: AuditTrail = Depends(get_audit),
) -> ExperimentSteward:
    return ExperimentSteward(store=store, audit=audit)


def get_reporter(
    store: ExperimentStore = Depends(get_store),
    audit: AuditTrail = Depends(get_audit),
) -> MetricsReporter:
    return MetricsReporter(store=store, audit=audit, clickhouse=InMemoryClickHousePort())


def get_proposer(
    audit: AuditTrail = Depends(get_audit),
) -> ChangeProposer:
    return ChangeProposer(audit=audit, github=InMemoryGitHubPort())


# ── Endpoints ─────────────────────────────────────────────────────────────


@router.post("/design", response_model=ComplianceExperiment, status_code=201)
async def design_experiment(
    request: DesignRequest,
    designer: ExperimentDesigner = Depends(get_designer),
) -> ComplianceExperiment:
    """Design a new compliance experiment from KB query.

    Queries the compliance KB, extracts citations, and creates a DRAFT
    experiment with auto-generated hypothesis and metrics baseline/target.

    Returns the created experiment in DRAFT status.
    """
    try:
        return designer.design(request)
    except Exception as exc:
        logger.error("Failed to design experiment: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("", response_model=list[ExperimentSummary])
async def list_experiments(
    status: str = Query(
        default="", description="Filter by status (draft/active/finished/rejected)"
    ),
    store: ExperimentStore = Depends(get_store),
) -> list[ExperimentSummary]:
    """List experiments, optionally filtered by status.

    Returns summary objects (id, title, scope, status, updated_at).
    """
    if status:
        try:
            exp_status = ExperimentStatus(status.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Must be one of: draft, active, finished, rejected",
            )
        return store.list_by_status(exp_status)
    return store.list_all()


@router.get("/metrics/current", response_model=dict[str, Any])
async def get_current_metrics(
    period_days: int = Query(default=1, ge=1, le=90, description="Lookback period in days"),
    reporter: MetricsReporter = Depends(get_reporter),
) -> dict[str, Any]:
    """Get current AML metrics snapshot from ClickHouse.

    Returns hit rate, false positive rate, SAR yield, review time,
    amount blocked (GBP), and cases reviewed for the given period.
    """
    metrics = reporter.get_current_metrics(period_days=period_days)
    return metrics.model_dump(mode="json")


@router.get("/{experiment_id}", response_model=ComplianceExperiment)
async def get_experiment(
    experiment_id: str,
    store: ExperimentStore = Depends(get_store),
) -> ComplianceExperiment:
    """Get full experiment details by ID."""
    exp = store.get(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return exp


@router.patch("/{experiment_id}/approve", response_model=ComplianceExperiment)
async def approve_experiment(
    experiment_id: str,
    request: ApproveRequest,
    steward: ExperimentSteward = Depends(get_steward),
) -> ComplianceExperiment:
    """Approve a DRAFT experiment → moves to ACTIVE.

    Validates hypothesis length, KB citations, metrics baseline/target.
    Raises 404 if not found, 422 if validation fails.
    """
    try:
        return steward.approve(experiment_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{experiment_id}/reject", response_model=ComplianceExperiment)
async def reject_experiment(
    experiment_id: str,
    request: RejectRequest,
    steward: ExperimentSteward = Depends(get_steward),
) -> ComplianceExperiment:
    """Reject a DRAFT experiment → moves to REJECTED.

    Requires a reason. Raises 404 if not found, 400 if not in DRAFT status.
    """
    try:
        return steward.reject(experiment_id, request)
    except ValueError as exc:
        status_code = 400 if "DRAFT" in str(exc) else 404
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/{experiment_id}/propose", response_model=ChangeProposal)
async def propose_change(
    experiment_id: str,
    request: ProposeRequest,
    store: ExperimentStore = Depends(get_store),
    proposer: ChangeProposer = Depends(get_proposer),
) -> ChangeProposal:
    """Propose a compliance change for an ACTIVE experiment.

    Creates a Git branch, renders a PR body with HITL checklist,
    and opens a GitHub PR + tracking issue.

    Use dry_run=true (default) to preview without creating branch/PR.
    """
    exp = store.get(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    try:
        return proposer.propose(exp, request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{experiment_id}/audit", response_model=list[AuditEntry])
async def get_audit_trail(
    experiment_id: str,
    store: ExperimentStore = Depends(get_store),
    audit: AuditTrail = Depends(get_audit),
) -> list[AuditEntry]:
    """Get the full audit trail for an experiment.

    Returns all audit entries logged for this experiment ID.
    FCA requirement: 7-year retention.
    """
    exp = store.get(experiment_id)
    if exp is None:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return audit.get_entries(experiment_id)
