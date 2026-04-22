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
    api_versioning,
    audit_dashboard,
    audit_trail,
    auth,
    batch_payments,
    beneficiary,
    card_issuing,
    compliance_automation,
    compliance_calendar,
    compliance_kb,
    compliance_sync,
    consent_management,
    consumer_duty,
    consumer_duty_v2,
    crypto_custody,
    customers,
    dispute_resolution,
    document_management,
    experiments,
    fee_management,
    fin060_reporting,
    fraud,
    fraud_tracer,
    fx_engine,
    fx_exchange,
    fx_rates,
    health,
    hitl,
    insurance,
    kyb_onboarding,
    kyc,
    ledger,
    lending,
    loyalty,
    merchant_acquiring,
    midaz_mcp,
    mlro_notifications,
    multi_currency,
    multi_tenancy,
    notifications,
    notifications_hub,
    observability,
    open_banking,
    payments,
    pgaudit,
    psd2_gateway,
    recon,
    referral,
    regulatory,
    reporting,
    reporting_analytics,
    risk_management,
    safeguarding,
    safeguarding_recon,
    sanctions_rescreen,
    sanctions_screening,
    savings,
    scheduled_payments,
    statements,
    support,
    swift_correspondent,
    transaction_monitor,
    treasury,
    user_preferences,
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
app.include_router(
    dispute_resolution.router
)  # Dispute Resolution & Chargeback (IL-DRM-01) — /v1/disputes/* embedded
app.include_router(
    beneficiary.router
)  # Beneficiary & Payee Management (IL-BPM-01) — /v1/beneficiaries/* embedded
app.include_router(
    crypto_custody.router
)  # Crypto & Digital Assets Custody (IL-CDC-01) — /v1/crypto/* embedded
app.include_router(
    batch_payments.router
)  # Batch Payment Processing (IL-BPP-01) — /v1/batch-payments/* embedded
app.include_router(
    risk_management.router, prefix=""
)  # Risk Management & Scoring Engine (IL-RMS-01) — /v1/risk/*
app.include_router(
    reporting_analytics.router, prefix=""
)  # Reporting & Analytics Platform (IL-RAP-01) — /v1/reports/*
app.include_router(
    user_preferences.router, prefix="/v1"
)  # User Preferences & Settings (IL-UPS-01) — /v1/preferences/*
app.include_router(
    audit_trail.router, prefix="/v1"
)  # Audit Trail & Event Sourcing (IL-AES-01) — /v1/audit-trail/*
app.include_router(fee_management.router)  # Fee Management Engine (IL-FME-01) — /v1/fees/*
app.include_router(
    compliance_calendar.router
)  # Compliance Calendar & Deadline Tracker (IL-CCD-01) — /v1/compliance-calendar/*
app.include_router(multi_tenancy.router)  # Multi-Tenancy Infrastructure (IL-MT-01) — /v1/tenants/*
app.include_router(
    api_versioning.router
)  # API Versioning & Deprecation (IL-AVD-01) — /v1/api-versions/*
app.include_router(
    kyb_onboarding.router, prefix="/v1/kyb"
)  # KYB Business Onboarding (IL-KYB-01) — /v1/kyb/*
app.include_router(
    sanctions_screening.router, prefix="/v1/sanctions"
)  # Sanctions Real-Time Screening (IL-SRS-01) — /v1/sanctions/*
app.include_router(
    swift_correspondent.router, prefix="/v1/swift"
)  # SWIFT & Correspondent Banking (IL-SWF-01) — /v1/swift/*
app.include_router(fx_engine.router, prefix="/v1/fx")  # FX Engine (IL-FXE-01) — /v1/fx/*
app.include_router(
    consent_management.router, prefix="/v1"
)  # Consent Management & TPP Registry (IL-CNS-01) — /v1/consent/*
app.include_router(
    consumer_duty_v2.router, prefix="/v1"
)  # Consumer Duty Outcome Monitoring (IL-CDO-01) — /v1/consumer-duty/* (Phase 50)
app.include_router(pgaudit.router, prefix="/v1")  # pgAudit Infrastructure (IL-PGA-01) — /v1/audit/*
app.include_router(
    safeguarding_recon.router, prefix="/v1"
)  # Daily Safeguarding Recon (IL-REC-01) — /v1/safeguarding-recon/*
app.include_router(
    fin060_reporting.router, prefix="/v1"
)  # FIN060 Regulatory Reporting (IL-FIN060-01) — /v1/fin060/*
app.include_router(
    fx_rates.router, prefix="/v1"
)  # FX Rates Frankfurter (IL-FXR-01) — /v1/fx-rates/*
app.include_router(
    psd2_gateway.router, prefix="/v1"
)  # PSD2 Gateway adorsys (IL-PSD2GW-01) — /v1/psd2/*
app.include_router(observability.router, prefix="/v1")  # Observability (IL-OBS-01)
app.include_router(compliance_sync.router, prefix="/v1")  # Compliance Matrix Sync (IL-CMS-01)
app.include_router(midaz_mcp.router, prefix="/v1")  # Midaz MCP Integration (IL-MCP-01)
app.include_router(fraud_tracer.router, prefix="/v1")  # Fraud Tracer (IL-TRC-01)
