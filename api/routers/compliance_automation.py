"""
api/routers/compliance_automation.py
IL-CAE-01 | Phase 23

Compliance Automation Engine REST API.

POST /v1/compliance/evaluate            — evaluate entity compliance
GET  /v1/compliance/rules               — list active rules (optional ?rule_type=)
GET  /v1/compliance/rules/{rule_id}     — get single rule
POST /v1/compliance/breach/report       — report breach to FCA (HITL, HTTP 202)
POST /v1/compliance/remediations        — create remediation tracking item
GET  /v1/compliance/remediations        — list open remediations
POST /v1/compliance/policies            — create new policy (DRAFT)
POST /v1/compliance/policies/diff       — diff two policy versions

FCA compliance:
  - HITL gate for FCA breach submissions (I-27) → HTTP 202
  - Append-only audit trail (I-24)
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.compliance_automation.breach_reporter import BreachReporter
from services.compliance_automation.compliance_automation_agent import (
    ComplianceAutomationAgent,
)
from services.compliance_automation.models import (
    _DEFAULT_RULES,
    InMemoryCheckStore,
    InMemoryPolicyStore,
    InMemoryRemediationStore,
    InMemoryReportStore,
    InMemoryRuleStore,
)
from services.compliance_automation.periodic_review import PeriodicReview
from services.compliance_automation.policy_manager import PolicyManager
from services.compliance_automation.remediation_tracker import RemediationTracker
from services.compliance_automation.rule_engine import RuleEngine

router = APIRouter(tags=["compliance-automation"])


# ── Pydantic request models ────────────────────────────────────────────────────


class EvaluateRequest(BaseModel):
    entity_id: str
    rule_ids: list[str] | None = None


class ReportBreachRequest(BaseModel):
    breach_id: str
    actor: str


class TrackRemediationRequest(BaseModel):
    check_id: str
    entity_id: str
    finding: str
    assigned_to: str
    due_days: int = 30


class PolicyCreateRequest(BaseModel):
    policy_id: str
    content: str
    author: str


class PolicyDiffRequest(BaseModel):
    policy_id: str
    v1: int
    v2: int


# ── Agent factory ──────────────────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _get_agent() -> ComplianceAutomationAgent:
    """Build ComplianceAutomationAgent wired to InMemory stubs, seeds default rules."""
    rule_store = InMemoryRuleStore()
    check_store = InMemoryCheckStore()
    report_store = InMemoryReportStore()
    remediation_store = InMemoryRemediationStore()
    policy_store = InMemoryPolicyStore()

    rule_engine = RuleEngine(rule_store, check_store)
    policy_manager = PolicyManager(policy_store)
    periodic_review = PeriodicReview(rule_store, check_store, report_store)
    breach_reporter = BreachReporter(check_store, report_store)
    remediation_tracker = RemediationTracker(remediation_store)

    # Seed default rules synchronously via internal dict access
    for rule in _DEFAULT_RULES:
        rule_store._rules[rule.rule_id] = rule  # noqa: SLF001

    return ComplianceAutomationAgent(
        rule_engine=rule_engine,
        policy_manager=policy_manager,
        periodic_review=periodic_review,
        breach_reporter=breach_reporter,
        remediation_tracker=remediation_tracker,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post("/v1/compliance/evaluate")
async def evaluate_compliance(req: EvaluateRequest) -> dict[str, Any]:
    """Evaluate an entity against active compliance rules."""
    agent = _get_agent()
    return await agent.evaluate_compliance(req.entity_id, req.rule_ids)


@router.get("/v1/compliance/rules")
async def list_rules(rule_type: str | None = None) -> list[dict[str, Any]]:
    """List active compliance rules, optionally filtered by rule_type."""
    agent = _get_agent()
    try:
        return await agent.get_rules(rule_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/v1/compliance/rules/{rule_id}")
async def get_rule(rule_id: str) -> dict[str, Any]:
    """Fetch a single compliance rule by ID."""
    agent = _get_agent()
    rules = await agent.get_rules()
    for rule in rules:
        if rule["rule_id"] == rule_id:
            return rule
    raise HTTPException(status_code=404, detail=f"Rule not found: {rule_id}")


@router.post("/v1/compliance/breach/report", status_code=202)
async def report_breach(req: ReportBreachRequest) -> dict[str, Any]:
    """Submit a breach for FCA reporting. Always returns HITL_REQUIRED (HTTP 202)."""
    agent = _get_agent()
    return await agent.report_breach(req.breach_id, req.actor)


@router.post("/v1/compliance/remediations")
async def create_remediation(req: TrackRemediationRequest) -> dict[str, Any]:
    """Create a remediation tracking item for a compliance finding."""
    agent = _get_agent()
    return await agent.track_remediation(
        check_id=req.check_id,
        entity_id=req.entity_id,
        finding=req.finding,
        assigned_to=req.assigned_to,
        due_days=req.due_days,
    )


@router.get("/v1/compliance/remediations")
async def list_remediations(entity_id: str | None = None) -> list[dict[str, Any]]:
    """List open remediation items, optionally filtered by entity_id."""
    agent = _get_agent()
    items = await agent._remediation_tracker.list_open_remediations(entity_id)  # noqa: SLF001
    return [
        {
            "remediation_id": r.remediation_id,
            "check_id": r.check_id,
            "entity_id": r.entity_id,
            "finding": r.finding,
            "status": r.status.value,
            "assigned_to": r.assigned_to,
            "due_date": r.due_date.isoformat(),
        }
        for r in items
    ]


@router.post("/v1/compliance/policies")
async def create_policy(req: PolicyCreateRequest) -> dict[str, Any]:
    """Create a new compliance policy in DRAFT status."""
    agent = _get_agent()
    return await agent.create_policy(req.policy_id, req.content, req.author)


@router.post("/v1/compliance/policies/diff")
async def get_policy_diff(req: PolicyDiffRequest) -> dict[str, Any]:
    """Compare content of two policy versions."""
    agent = _get_agent()
    try:
        return await agent.get_policy_diff(req.policy_id, req.v1, req.v2)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
