"""
api/routers/transaction_monitor.py — Transaction Monitor REST API
IL-RTM-01 | banxe-emi-stack

Endpoints:
  POST  /v1/monitor/score            — score a transaction event
  GET   /v1/monitor/alerts           — list alerts (filter by severity/status)
  GET   /v1/monitor/alerts/{id}      — alert detail + explanation
  PATCH /v1/monitor/alerts/{id}      — update alert status
  GET   /v1/monitor/velocity/{cid}   — customer velocity metrics
  GET   /v1/monitor/metrics          — dashboard aggregate metrics
  POST  /v1/monitor/backtest         — backtest rules on historical data
  GET   /v1/monitor/health           — health check
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from services.transaction_monitor.alerts.alert_generator import AlertGenerator
from services.transaction_monitor.alerts.alert_router import AlertRouter, InMemoryMarblePort
from services.transaction_monitor.alerts.explanation_engine import InMemoryKBPort
from services.transaction_monitor.models.alert import (
    AlertSeverity,
    AlertStatus,
    AlertUpdateRequest,
    AMLAlert,
    BacktestRequest,
    BacktestResult,
)
from services.transaction_monitor.models.transaction import TransactionEvent
from services.transaction_monitor.scoring.risk_scorer import InMemoryMLModel, RiskScorer
from services.transaction_monitor.scoring.velocity_tracker import InMemoryVelocityTracker
from services.transaction_monitor.store.alert_store import AlertStorePort, InMemoryAlertStore

logger = logging.getLogger("banxe.api.monitor")

router = APIRouter(prefix="/monitor", tags=["transaction_monitor"])

# ── Dependency providers ──────────────────────────────────────────────────


def get_alert_store() -> AlertStorePort:
    return InMemoryAlertStore()


def get_velocity_tracker() -> InMemoryVelocityTracker:
    return InMemoryVelocityTracker()


def get_scorer(
    velocity: InMemoryVelocityTracker = Depends(get_velocity_tracker),
) -> RiskScorer:
    return RiskScorer(velocity_tracker=velocity, ml_model=InMemoryMLModel())


def get_generator(
    store: AlertStorePort = Depends(get_alert_store),
) -> AlertGenerator:
    return AlertGenerator(kb_port=InMemoryKBPort(), alert_store=store)


def get_router_dep(
    store: AlertStorePort = Depends(get_alert_store),
) -> AlertRouter:
    return AlertRouter(marble_port=InMemoryMarblePort(), alert_store=store)


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check for transaction monitor service."""
    return {"status": "ok", "service": "transaction_monitor", "il": "IL-RTM-01"}


@router.post("/score", response_model=dict[str, Any])
async def score_transaction(
    event: TransactionEvent,
    scorer: RiskScorer = Depends(get_scorer),
    generator: AlertGenerator = Depends(get_generator),
    alert_router: AlertRouter = Depends(get_router_dep),
) -> dict[str, Any]:
    """Score a transaction event and generate/route an AML alert.

    Returns the risk score and the generated alert (if any).
    CRITICAL and HIGH alerts are automatically routed to Marble.
    LOW alerts are auto-closed with audit log.
    """
    try:
        risk_score = scorer.score(event)
        alert = generator.generate(event, risk_score)
        routed_alert = alert_router.route(alert)
        return {
            "transaction_id": event.transaction_id,
            "risk_score": risk_score.model_dump(mode="json"),
            "alert": routed_alert.model_dump(mode="json"),
        }
    except Exception as exc:
        logger.error("Failed to score transaction %s: %s", event.transaction_id, exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/alerts", response_model=list[AMLAlert])
async def list_alerts(
    severity: str = Query(default="", description="Filter by severity: low/medium/high/critical"),
    status: str = Query(
        default="", description="Filter by status: open/reviewing/escalated/closed/auto_closed"
    ),
    customer_id: str = Query(default="", description="Filter by customer ID"),
    limit: int = Query(default=50, ge=1, le=200),
    store: AlertStorePort = Depends(get_alert_store),
) -> list[AMLAlert]:
    """List AML alerts with optional filters."""
    sev = None
    if severity:
        try:
            sev = AlertSeverity(severity.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")

    stat = None
    if status:
        try:
            stat = AlertStatus(status.lower())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    return store.list_alerts(
        severity=sev,
        status=stat,
        customer_id=customer_id or None,
        limit=limit,
    )


@router.get("/alerts/{alert_id}", response_model=AMLAlert)
async def get_alert(
    alert_id: str,
    store: AlertStorePort = Depends(get_alert_store),
) -> AMLAlert:
    """Get full alert details including explanation and KB citations."""
    alert = store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return alert


@router.patch("/alerts/{alert_id}", response_model=AMLAlert)
async def update_alert(
    alert_id: str,
    update: AlertUpdateRequest,
    store: AlertStorePort = Depends(get_alert_store),
) -> AMLAlert:
    """Update alert status (reviewing / escalated / closed).

    HITL invariant: CRITICAL alerts require human sign-off before closure.
    """
    alert = store.get(alert_id)
    if alert is None:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")

    # HITL gate: CRITICAL alerts cannot be auto-closed via API without notes
    if (
        alert.severity == AlertSeverity.CRITICAL
        and update.status == AlertStatus.CLOSED
        and not update.notes
    ):
        raise HTTPException(
            status_code=422,
            detail="CRITICAL alert closure requires reviewer notes (HITL gate)",
        )

    alert.status = update.status
    if update.assigned_to:
        alert.assigned_to = update.assigned_to
    if update.closure_reason:
        alert.closure_reason = update.closure_reason
    alert.audit_trail.append(
        {
            "action": f"status_update_{update.status.value}",
            "notes": update.notes,
            "assigned_to": update.assigned_to,
        }
    )
    store.save(alert)
    return alert


@router.get("/velocity/{customer_id}", response_model=dict[str, Any])
async def get_velocity(
    customer_id: str,
    velocity: InMemoryVelocityTracker = Depends(get_velocity_tracker),
) -> dict[str, Any]:
    """Get velocity metrics for a customer across all time windows."""
    from services.transaction_monitor.config import get_config

    config = get_config()
    return {
        "customer_id": customer_id,
        "velocity": {
            "1h": {
                "count": velocity.get_count(customer_id, "1h"),
                "threshold": config.velocity_1h_threshold,
                "exceeded": velocity.get_count(customer_id, "1h") > config.velocity_1h_threshold,
            },
            "24h": {
                "count": velocity.get_count(customer_id, "24h"),
                "threshold": config.velocity_24h_threshold,
                "exceeded": velocity.get_count(customer_id, "24h") > config.velocity_24h_threshold,
            },
            "7d": {
                "count": velocity.get_count(customer_id, "7d"),
                "threshold": config.velocity_7d_threshold,
                "exceeded": velocity.get_count(customer_id, "7d") > config.velocity_7d_threshold,
            },
        },
        "cumulative_gbp_24h": str(velocity.get_cumulative_amount(customer_id, "24h")),
        "requires_edd": velocity.requires_edd(customer_id),
    }


@router.get("/metrics", response_model=dict[str, Any])
async def get_metrics(
    store: AlertStorePort = Depends(get_alert_store),
) -> dict[str, Any]:
    """Get aggregate monitoring metrics for dashboard.

    Returns alert counts by severity, open/closed breakdown,
    and estimated SAR yield.
    """
    counts_by_severity = store.count_by_severity()
    total = sum(counts_by_severity.values())
    open_alerts = len(store.list_alerts(status=AlertStatus.OPEN, limit=1000))
    escalated = len(store.list_alerts(status=AlertStatus.ESCALATED, limit=1000))

    # SAR yield estimate: critical alerts / total (simplified)
    critical_count = counts_by_severity.get("critical", 0)
    sar_yield_estimate = (
        (critical_count / total) if total > 0 else 0.0
    )  # nosemgrep: banxe-float-money — non-monetary rate

    return {
        "total_alerts": total,
        "by_severity": counts_by_severity,
        "open_alerts": open_alerts,
        "escalated_alerts": escalated,
        "sar_yield_estimate": round(sar_yield_estimate, 4),
        "targets": {
            "false_positive_target": 0.35,
            "sar_yield_target": 0.20,
            "review_sla_hours": 24,
        },
    }


@router.post("/backtest", response_model=BacktestResult)
async def backtest(
    request: BacktestRequest,
    scorer: RiskScorer = Depends(get_scorer),
) -> BacktestResult:
    """Backtest scoring rules on historical data.

    Generates synthetic transactions for the specified period
    and returns estimated hit rate and SAR yield improvement.
    """
    from decimal import Decimal as D

    # Deterministic sample for backtest (no external deps)
    sample_txns = []
    delta = request.to_date - request.from_date
    step = delta / max(request.sample_size, 1)

    for i in range(min(request.sample_size, 100)):
        ts = request.from_date + step * i
        event = TransactionEvent(
            transaction_id=f"BT-{i:06d}",
            timestamp=ts,
            amount=D(str(1000 + (i % 20) * 500)),
            sender_id=f"cust-{i % 50:04d}",
            sender_jurisdiction="GB",
        )
        sample_txns.append(scorer.score(event))

    total = len(sample_txns)
    alerts_generated = sum(1 for s in sample_txns if s.score >= 0.30)
    critical = sum(1 for s in sample_txns if s.score >= 0.80)

    hit_rate = (
        alerts_generated / total if total else 0.0
    )  # nosemgrep: banxe-float-money — non-monetary rate
    sar_yield_est = (
        critical / total if total else 0.0
    )  # nosemgrep: banxe-float-money — non-monetary rate

    return BacktestResult(
        from_date=request.from_date,
        to_date=request.to_date,
        total_transactions=total,
        alerts_generated=alerts_generated,
        hit_rate=round(hit_rate, 4),
        false_positive_estimate=round(
            1.0 - hit_rate, 4
        ),  # nosemgrep: banxe-float-money — non-monetary
        sar_yield_estimate=round(sar_yield_est, 4),
        improvement_vs_baseline=round(
            sar_yield_est - 0.065, 4
        ),  # nosemgrep: banxe-float-money — vs 6.5% baseline
        notes=f"Backtest on {total} synthetic transactions ({request.from_date.date()} to {request.to_date.date()})",
    )
