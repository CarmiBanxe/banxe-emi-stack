# UI Map — banxe-emi-stack
# Source: api/routers/, api/main.py, config/banxe_config.yaml, agents/compliance/swarm.yaml
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14: SCA challenge component in banxe-platform/web)
# Migration Phase: 5
# Purpose: Complete screen inventory for web and mobile apps

## Current state

No custom UI exists in banxe-emi-stack (backend-only repo).
FastAPI auto-generates Swagger UI (/docs) and ReDoc (/redoc).
CORS is configured for `localhost:3000` and `localhost:5173` (dev origins).

## External UIs (deployed on GMKtec, not part of this repo)

| UI | Port | Purpose | Users | Status |
|----|------|---------|-------|--------|
| Ballerine Backoffice | :5137 | KYC case review & workflow management | Compliance Officer | ✅ |
| Marble Dashboard | :5002/:5003 | Transaction monitoring & case management | MLRO, Compliance Officer | ✅ |
| n8n Editor | :5678 | Workflow automation & alert management | Ops, CTIO | ✅ |
| Keycloak Admin | :8180 | IAM, role management, realm config | Admin | ✅ |
| Swagger UI | :8000/docs | API explorer (auto-generated) | Developers | ✅ |
| ReDoc | :8000/redoc | API documentation (auto-generated) | Developers | ✅ |

## Candidate screen inventory (derived from 42 API endpoints)

### Customer-facing screens (external users)

| # | Screen | API endpoints consumed | Priority |
|---|--------|----------------------|----------|
| C-01 | Login / Register | Keycloak OIDC flow (external) | P1 |
| C-02 | Dashboard (Home) | GET /v1/ledger/accounts, GET /v1/ledger/accounts/{id}/balance | P1 |
| C-03 | Account Overview | GET /v1/ledger/accounts/{id}/balance, GET /v1/payments | P1 |
| C-04 | Send Payment | POST /v1/payments, POST /v1/fraud/assess (pre-gate) | P1 |
| C-05 | Payment Status | GET /v1/payments/{key}, GET /v1/notifications/{id}/status | P1 |
| C-06 | Transaction History | GET /v1/payments, GET /v1/ledger/accounts | P1 |
| C-07 | KYC Onboarding | POST /v1/kyc/workflows, POST /v1/kyc/workflows/{id}/documents | P1 |
| C-08 | KYC Status | GET /v1/kyc/workflows/{id} | P2 |
| C-09 | Profile / Settings | GET /v1/customers/{id}, POST /v1/customers/{id}/lifecycle | P2 |
| C-10 | Notifications | GET /v1/notifications/{id}/status, GET /v1/notifications/preview | P2 |
| C-11 | Statements Download | (not yet built — needs new endpoint) | P2 |

### Internal operations screens (staff)

| # | Screen | API endpoints consumed | Role | Priority |
|---|--------|----------------------|------|----------|
| I-01 | MLRO Dashboard | GET /v1/reporting/sar, GET /v1/reporting/sar/stats, GET /v1/hitl/stats | MLRO | P1 |
| I-02 | HITL Review Queue | GET /v1/hitl/queue, POST /v1/hitl/queue/{id}/decide | MLRO, CO | P1 |
| I-03 | HITL Case Detail | GET /v1/hitl/queue/{id}, POST /v1/hitl/queue/{id}/decide | MLRO, CO | P1 |
| I-04 | SAR Management | POST /v1/reporting/sar, GET /v1/reporting/sar/{id} | MLRO | P1 |
| I-05 | SAR Detail / Approve | POST /v1/reporting/sar/{id}/approve, /submit, /withdraw | MLRO | P1 |
| I-06 | FIN060 Dashboard | POST /v1/reporting/fin060/generate, /submit | CFO, MLRO | P1 |
| I-07 | Safeguarding Recon Status | (needs new endpoint — reads ClickHouse directly) | Ops | P1 |
| I-08 | Customer Management | GET /v1/customers, POST /v1/customers, GET /v1/customers/{id} | Ops | P1 |
| I-09 | KYC Management | POST /v1/kyc/workflows, POST .../approve-edd, /reject | CO | P1 |
| I-10 | Fraud Assessment | POST /v1/fraud/assess | Fraud Analyst | P2 |
| I-11 | Consumer Duty | POST /v1/consumer-duty/vulnerability, /fair-value, /outcomes, /report | CO | P2 |
| I-12 | Consumer Duty Reports | GET /v1/consumer-duty/vulnerability/{id} | CO, Board | P2 |
| I-13 | Notifications Manager | POST /v1/notifications/send, GET .../preview | Ops | P2 |
| I-14 | MLRO Alerts | POST /internal/notifications/mlro | MLRO | P2 |
| I-15 | Sanctions Rescreen | POST /compliance/sanctions/rescreen/high-risk | MLRO | P2 |

### System/webhook screens (no UI — API-only)

| # | Endpoint | Purpose | UI needed |
|---|----------|---------|-----------|
| S-01 | GET /health, GET /health/ready | Health checks | No — monitoring tools |
| S-02 | POST /webhooks/watchman | Watchman list update | No — webhook receiver |

## Screen-to-endpoint coverage matrix

| Screen category | Screens | Endpoints covered | Endpoints not covered |
|----------------|---------|-------------------|----------------------|
| Customer-facing | 11 | 16 | 2 (statements, FX rates) |
| Internal ops | 15 | 24 | 3 (recon status, audit export, deploy) |
| System/webhooks | 2 | 4 | 0 |
| **Total** | **28** | **40/42** | **5 gaps** |

## Uncovered gaps (no existing endpoint)

| Gap | Needed for screen | Proposed endpoint | Priority |
|-----|-------------------|-------------------|----------|
| G-01 | Statement download (C-11) | GET /v1/statements/{account_id} | P2 |
| G-02 | Recon status dashboard (I-07) | GET /v1/recon/status, GET /v1/recon/history | P1 |
| G-03 | FX rate lookup (C-04) | GET /v1/fx/rates?from=GBP&to=EUR | P2 |
| G-04 | Audit export trigger (I-07) | POST /v1/audit/export | P3 |
| G-05 | Account opening | POST /v1/accounts | P1 |

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*
