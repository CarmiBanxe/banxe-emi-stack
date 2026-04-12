"""
services/experiment_copilot/agents/experiment_designer.py — Experiment Designer
IL-CEC-01 | banxe-emi-stack

Designs new compliance experiments from KB queries and AML baselines.
Queries Compliance KB (Part 1) → identifies coverage gaps → creates draft YAML.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

import yaml

from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    DesignRequest,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore

logger = logging.getLogger("banxe.experiment_copilot.designer")


# ── KB Port (Protocol DI) ──────────────────────────────────────────────────


@runtime_checkable
class KBQueryPort(Protocol):
    """Interface for querying the Compliance KB (Part 1)."""

    def query_kb(self, notebook_id: str, question: str, max_citations: int = 5) -> dict[str, Any]:
        """Return {answer: str, citations: list[dict]}."""
        ...


# ── InMemory stub for tests ────────────────────────────────────────────────


class InMemoryKBPort:
    """Test stub — returns deterministic KB responses."""

    def query_kb(self, notebook_id: str, question: str, max_citations: int = 5) -> dict[str, Any]:
        return {
            "answer": f"Regulatory context for: {question}",
            "citations": [
                {
                    "source_id": "eba-gl-2021-02",
                    "title": "EBA Guidelines on ML/TF risk factors",
                    "section": "Section 4.2",
                    "snippet": "EMIs must apply risk-based velocity controls.",
                    "version": "2021-06-01",
                }
            ],
        }


# ── HTTP KB Port (production) ──────────────────────────────────────────────


class HTTPKBPort:
    """Production KB port — calls the FastAPI /v1/kb/query endpoint."""

    def __init__(self, api_base: str = "http://localhost:8000") -> None:
        self._api_base = api_base

    def query_kb(self, notebook_id: str, question: str, max_citations: int = 5) -> dict[str, Any]:
        import httpx

        with httpx.Client(base_url=self._api_base, timeout=15.0) as client:
            r = client.post(
                "/v1/kb/query",
                json={
                    "notebook_id": notebook_id,
                    "question": question,
                    "max_citations": max_citations,
                },
            )
            r.raise_for_status()
            return r.json()


# ── Designer ───────────────────────────────────────────────────────────────

# Notebook selection per scope
_SCOPE_NOTEBOOKS = {
    ExperimentScope.TRANSACTION_MONITORING: "emi-eu-aml",
    ExperimentScope.KYC_ONBOARDING: "emi-uk-fca",
    ExperimentScope.CASE_MANAGEMENT: "emi-eu-aml",
    ExperimentScope.SAR_FILING: "emi-eu-aml",
    ExperimentScope.RISK_SCORING: "emi-eu-aml",
}


class ExperimentDesigner:
    """Designs new compliance experiments from KB queries.

    Workflow:
    1. Query the appropriate KB notebook for the given scope
    2. Extract KB citations to support the hypothesis
    3. Generate an experiment ID and draft ComplianceExperiment
    4. Persist to the experiment store as DRAFT
    5. Log to audit trail
    """

    def __init__(
        self,
        store: ExperimentStore,
        audit: AuditTrail,
        kb_port: KBQueryPort | None = None,
        baselines_path: str = "config/aml_baselines.yaml",
    ) -> None:
        self._store = store
        self._audit = audit
        self._kb = kb_port or InMemoryKBPort()
        self._baselines = self._load_baselines(baselines_path)

    def design(self, request: DesignRequest) -> ComplianceExperiment:
        """Design a new compliance experiment.

        1. Query KB for regulatory context
        2. Build hypothesis with citations
        3. Set metrics baseline/target from baselines config
        4. Save as DRAFT
        5. Audit log

        Args:
            request: DesignRequest with KB query, scope, and metadata.

        Returns:
            The created ComplianceExperiment in DRAFT status.
        """
        notebook_id = _SCOPE_NOTEBOOKS.get(request.scope, "emi-eu-aml")
        kb_result = self._kb.query_kb(
            notebook_id=notebook_id,
            question=request.query,
        )

        citations = [c.get("source_id", "") for c in kb_result.get("citations", [])]
        answer = kb_result.get("answer", "")

        exp_id = self._generate_id(request.scope, request.query)
        title = self._generate_title(request.query, request.scope)
        hypothesis = self._generate_hypothesis(request.query, answer, request.scope)
        baseline, target = self._get_metrics_for_scope(request.scope)

        experiment = ComplianceExperiment(
            id=exp_id,
            title=title,
            scope=request.scope,
            status=ExperimentStatus.DRAFT,
            hypothesis=hypothesis,
            kb_citations=citations,
            created_by=request.created_by,
            tags=request.tags + [request.scope.value],
            metrics_baseline=baseline,
            metrics_target=target,
        )

        self._store.save(experiment)
        self._audit.log(
            actor=request.created_by,
            action="experiment.created",
            experiment_id=exp_id,
            details={
                "scope": request.scope.value,
                "query": request.query,
                "citations": citations,
                "notebook": notebook_id,
            },
        )

        logger.info("Designed experiment %s (%s)", exp_id, request.scope.value)
        return experiment

    # ── Helpers ────────────────────────────────────────────────────────────

    def _generate_id(self, scope: ExperimentScope, query: str) -> str:
        date_str = datetime.utcnow().strftime("%Y-%m")
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:30].strip("-")
        short_scope = scope.value.split("_")[0][:4]
        return f"exp-{date_str}-{short_scope}-{slug}"

    def _generate_title(self, query: str, scope: ExperimentScope) -> str:
        scope_label = scope.value.replace("_", " ").title()
        return f"{scope_label}: {query[:80]}"

    def _generate_hypothesis(self, query: str, kb_answer: str, scope: ExperimentScope) -> str:
        return (
            f"By implementing changes related to '{query}', "
            f"we expect to improve {scope.value.replace('_', ' ')} performance metrics. "
            f"Regulatory basis: {kb_answer[:300]}"
        )

    def _get_metrics_for_scope(
        self, scope: ExperimentScope
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        if not self._baselines:
            return {}, {}
        baselines = self._baselines.get("baselines", {})
        baseline = {
            "hit_rate_24h": baselines.get("hit_rate_24h", {}).get("current"),
            "false_positive_rate": baselines.get("false_positive_rate", {}).get("current"),
            "sar_yield": baselines.get("sar_yield", {}).get("current"),
        }
        target = {
            "hit_rate_24h": baselines.get("hit_rate_24h", {}).get("target"),
            "false_positive_rate": baselines.get("false_positive_rate", {}).get("target"),
            "sar_yield": baselines.get("sar_yield", {}).get("target"),
        }
        return baseline, target

    def _load_baselines(self, path: str) -> dict[str, Any]:
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return {}
        with open(p, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
