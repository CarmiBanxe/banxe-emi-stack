"""
api/main.py — Banxe EMI FastAPI REST API Layer
IL-046 | S17-01 | S18-01 | banxe-emi-stack

Single entry point for all REST API routes. Exposes:
  GET  /health                   — liveness + readiness
  POST /v1/customers             — onboard customer
  GET  /v1/customers/{id}        — fetch customer profile
  POST /v1/kyc/workflows         — start KYC workflow
  GET  /v1/kyc/workflows/{id}    — get KYC status
  POST /v1/kyc/workflows/{id}/documents — submit documents
  POST /v1/payments              — initiate payment
  GET  /v1/payments/{id}         — get payment status
  GET  /v1/ledger/accounts       — list ledger accounts
  GET  /v1/ledger/accounts/{id}/balance — get account balance
  POST /v1/auth/sca/challenge    — initiate PSD2 SCA challenge (Art.97)
  POST /v1/auth/sca/verify       — verify SCA challenge, receive dynamic-linking token
  GET  /v1/auth/sca/methods/{id} — available SCA methods for customer
  POST /v1/auth/token/refresh    — rotate refresh token, issue new access token (PSD2 RTS)

FCA compliance:
  - All requests logged with X-Request-ID (I-24 audit trail)
  - Amounts always Decimal / string, never float (I-05)
  - No PII in logs (I-09)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import (
    api_gateway,
    audit_dashboard,
    auth,
    card_issuing,
    compliance_automation,
    compliance_kb,
    consumer_duty,
    customers,
    document_management,
    experiments,
    fraud,
    fx_exchange,
    health,
    hitl,
    insurance,
    kyc,
    ledger,
    lending,
    loyalty,
    merchant_acquiring,
    mlro_notifications,
    multi_currency,
    notifications,
    notifications_hub,
    open_banking,
    payments,
    recon,
    referral,
    regulatory,
    reporting,
    safeguarding,
    sanctions_rescreen,
    savings,
    scheduled_payments,
    statements,
    support,
    transaction_monitor,
    treasury,
    watchman_webhook,
    webhook_orchestrator,
)

logger = logging.getLogger("banxe.api")


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    """Startup / shutdown lifecycle."""
    logger.info("Banxe API starting up (IL-046)")
    yield
    logger.info("Banxe API shutting down")


app = FastAPI(
    title="Banxe EMI REST API",
    description="FCA-authorised EMI platform — payment, KYC, customer, ledger",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],  # Dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request-ID middleware (FCA audit trail I-24) ───────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):  # type: ignore[return]
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ── Global error handler ──────────────────────────────────────────────────
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID", "unknown")
    logger.error("Unhandled exception request_id=%s type=%s", request_id, type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(auth.router, prefix="/v1")
app.include_router(customers.router, prefix="/v1")
app.include_router(kyc.router, prefix="/v1")
app.include_router(payments.router, prefix="/v1")
app.include_router(ledger.router, prefix="/v1")
app.include_router(notifications.router, prefix="/v1")
app.include_router(fraud.router, prefix="/v1")
app.include_router(consumer_duty.router, prefix="/v1")
app.include_router(hitl.router, prefix="/v1")
app.include_router(reporting.router, prefix="/v1")
app.include_router(statements.router, prefix="/v1")
app.include_router(watchman_webhook.router)  # POST /webhooks/watchman (IL-068)
app.include_router(mlro_notifications.router)  # POST /internal/notifications/mlro (IL-068)
app.include_router(
    sanctions_rescreen.router
)  # POST /compliance/sanctions/rescreen/high-risk (IL-068)
app.include_router(compliance_kb.router)  # GET/POST /v1/kb/* (IL-CKS-01)
app.include_router(experiments.router, prefix="/v1")  # GET/POST /v1/experiments/* (IL-CEC-01)
app.include_router(transaction_monitor.router, prefix="/v1")  # GET/POST /v1/monitor/* (IL-RTM-01)
app.include_router(safeguarding.router, prefix="/v1")  # CASS 15 safeguarding (6 endpoints)
app.include_router(recon.router, prefix="/v1")  # Reconciliation (3 endpoints)
app.include_router(support.router, prefix="/v1")  # Customer Support Block (IL-CSB-01)
app.include_router(regulatory.router, prefix="/v1")  # Regulatory Reporting (IL-RRA-01)
app.include_router(open_banking.router, prefix="/v1")  # Open Banking PSD2 Gateway (IL-OBK-01)
app.include_router(audit_dashboard.router, prefix="/v1")  # Audit & Governance Dashboard (IL-AGD-01)
app.include_router(treasury.router, prefix="/v1")  # Treasury & Liquidity Management (IL-TLM-01)
app.include_router(notifications_hub.router, prefix="/v1")  # Notification Hub (IL-NHB-01)
app.include_router(card_issuing.router, prefix="/v1")  # Card Issuing & Management (IL-CIM-01)
app.include_router(
    merchant_acquiring.router, prefix="/v1"
)  # Merchant Acquiring Gateway (IL-MAG-01)
app.include_router(fx_exchange.router)  # FX & Currency Exchange (IL-FXE-01) — /v1/fx/* embedded
app.include_router(multi_currency.router, prefix="/v1")  # Multi-Currency Ledger (IL-MCL-01)
app.include_router(
    compliance_automation.router
)  # Compliance Automation Engine (IL-CAE-01) — /v1/compliance/* embedded
app.include_router(
    document_management.router
)  # Document Management System (IL-DMS-01) — /v1/documents/* embedded
app.include_router(lending.router)  # Lending & Credit Engine (IL-LCE-01) — /v1/lending/* embedded
app.include_router(insurance.router)  # Insurance Integration (IL-INS-01) — /v1/insurance/* embedded
app.include_router(
    api_gateway.router
)  # API Gateway & Rate Limiting (IL-AGW-01) — /v1/gateway/* embedded
app.include_router(
    webhook_orchestrator.router
)  # Webhook Orchestrator (IL-WHO-01) — /v1/webhooks/* embedded
app.include_router(loyalty.router)  # Loyalty & Rewards (IL-LRE-01) — /v1/loyalty/* embedded
app.include_router(referral.router)  # Referral Program (IL-REF-01) — /v1/referral/* embedded
app.include_router(savings.router)  # Savings & Interest Engine (IL-SIE-01) — /v1/savings/* embedded
app.include_router(
    scheduled_payments.router
)  # Standing Orders & Direct Debits (IL-SOD-01) — /v1/standing-orders/* + /v1/direct-debits/* embedded
