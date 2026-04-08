"""
api/main.py — Banxe EMI FastAPI REST API Layer
IL-046 | S17-01 | banxe-emi-stack

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

FCA compliance:
  - All requests logged with X-Request-ID (I-24 audit trail)
  - Amounts always Decimal / string, never float (I-05)
  - No PII in logs (I-09)
"""
from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import customers, fraud, health, kyc, ledger, notifications, payments

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
    logger.error(
        "Unhandled exception request_id=%s type=%s", request_id, type(exc).__name__
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id},
    )


# ── Routers ───────────────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(customers.router, prefix="/v1")
app.include_router(kyc.router, prefix="/v1")
app.include_router(payments.router, prefix="/v1")
app.include_router(ledger.router, prefix="/v1")
app.include_router(notifications.router, prefix="/v1")
app.include_router(fraud.router, prefix="/v1")
