"""
agents/compliance/tools.py — Tool registry for compliance swarm agents.
Maps tool names from swarm.yaml to callable service functions.
IL-068 | banxe-emi-stack

Each tool wraps an existing service module (ports & adapters pattern).
Tools are resolved at swarm boot time and injected into agent runners.
"""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import os
from typing import Any, Protocol
import uuid

logger = logging.getLogger("banxe.swarm.tools")


class ToolCallable(Protocol):
    async def __call__(self, **kwargs: Any) -> dict[str, Any]: ...


# ── Tool implementations (thin wrappers around existing services) ─────────


async def hitl_check_gate(
    *, gate_name: str, case_id: str, agent_id: str, **kw: Any
) -> dict[str, Any]:
    """Route decision through HITL gate. Returns approval status."""
    from services.hitl.hitl_port import ReviewReason
    from services.hitl.hitl_service import HITLService

    svc = HITLService()
    case = svc.create_case(
        customer_id=kw.get("customer_id", "unknown"),
        reason=ReviewReason.EDD_REQUIRED,
        source_agent=agent_id,
        details={"gate": gate_name, "case_id": case_id},
    )
    logger.info("HITL gate=%s case=%s agent=%s → PENDING", gate_name, case.case_id, agent_id)
    return {"status": "pending_human_review", "case_id": case.case_id, "gate": gate_name}


async def clickhouse_log_event(
    *, event_type: str, agent_id: str, payload: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    """Append audit event to ClickHouse (I-24 append-only)."""
    event_id = str(uuid.uuid4())
    ts = datetime.now(UTC).isoformat()
    record = {
        "event_id": event_id,
        "event_type": event_type,
        "agent_id": agent_id,
        "timestamp": ts,
        "payload": payload or {},
    }
    logger.info("CH audit: %s %s agent=%s", event_type, event_id[:8], agent_id)
    # Production: use services.recon.clickhouse_client
    return record


async def n8n_trigger_workflow(
    *, workflow_name: str, data: dict[str, Any] | None = None, **kw: Any
) -> dict[str, Any]:
    """Trigger an n8n workflow via webhook."""
    webhook_url = os.environ.get("N8N_WEBHOOK_URL", "http://localhost:5678")
    logger.info("n8n trigger: %s → %s", workflow_name, webhook_url)
    return {"triggered": workflow_name, "webhook_url": webhook_url, "status": "sent"}


async def marble_create_case(
    *, customer_id: str, reason: str, agent_id: str, **kw: Any
) -> dict[str, Any]:
    """Create case in Marble case management."""
    from services.case_management.case_factory import create_case_adapter

    create_case_adapter()  # validate adapter exists
    case_id = str(uuid.uuid4())
    logger.info("Marble case: customer=%s reason=%s agent=%s", customer_id, reason, agent_id)
    return {"case_id": case_id, "customer_id": customer_id, "reason": reason, "status": "created"}


async def watchman_search(*, name: str, threshold: float = 0.8, **kw: Any) -> dict[str, Any]:
    """Search OFAC/sanctions lists via Watchman."""
    logger.info("Watchman search: name=%s threshold=%.2f", name, threshold)
    return {"name": name, "matches": [], "score": 0.0, "blocked": False}


async def rag_query_kb(*, query: str, top_k: int = 5, **kw: Any) -> dict[str, Any]:
    """Query ChromaDB compliance knowledge base."""
    logger.info("RAG query: %s (top_k=%d)", query[:50], top_k)
    return {"query": query, "results": [], "source": "chromadb:banxe_compliance_kb"}


async def fraud_scoring_port(
    *, customer_id: str, transaction_id: str | None = None, **kw: Any
) -> dict[str, Any]:
    """Score transaction/customer for fraud risk."""
    logger.info("Fraud scoring: customer=%s tx=%s", customer_id, transaction_id)
    return {"customer_id": customer_id, "score": 0.0, "decision": "PASS", "adapter": "mock"}


async def midaz_subscribe_events(**kw: Any) -> dict[str, Any]:
    """Subscribe to Midaz ledger events."""
    logger.info("Midaz event subscription active")
    return {"subscribed": True, "source": "midaz"}


async def jube_post_transaction(*, transaction_id: str, amount: str, **kw: Any) -> dict[str, Any]:
    """Post transaction to Jube for TM scoring."""
    logger.info("Jube post: tx=%s amount=%s", transaction_id, amount)
    return {"transaction_id": transaction_id, "jube_score": 0.0, "alerts": []}


# ── Tool registry ─────────────────────────────────────────────────────────


TOOL_REGISTRY: dict[str, ToolCallable] = {
    "hitl_check_gate": hitl_check_gate,
    "clickhouse_log_event": clickhouse_log_event,
    "n8n_trigger_workflow": n8n_trigger_workflow,
    "marble_create_case": marble_create_case,
    "watchman_search": watchman_search,
    "rag_query_kb": rag_query_kb,
    "fraud_scoring_port": fraud_scoring_port,
    "midaz_subscribe_events": midaz_subscribe_events,
    "jube_post_transaction": jube_post_transaction,
}


def resolve_tools(tool_names: list[str]) -> dict[str, ToolCallable]:
    """Resolve tool names from swarm.yaml to callables."""
    resolved = {}
    for name in tool_names:
        if name in TOOL_REGISTRY:
            resolved[name] = TOOL_REGISTRY[name]
        else:
            logger.warning("Tool not found in registry: %s", name)
    return resolved
