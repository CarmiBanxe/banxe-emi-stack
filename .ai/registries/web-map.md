# Web Map — banxe-emi-stack
# Source: api/main.py, api/routers/, config/banxe_config.yaml, ROADMAP.md
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14)
# Migration Phase: 5
# Purpose: Web app architecture analysis and readiness assessment

## Current state

No web frontend exists. Backend is production-ready with 42 REST endpoints.

### Existing web-accessible surfaces

| Surface | URL | Type | Auth |
|---------|-----|------|------|
| FastAPI REST API | http://localhost:8000/v1/ | JSON API | Keycloak OIDC (planned) |
| Swagger UI | http://localhost:8000/docs | Interactive docs | None (dev only) |
| ReDoc | http://localhost:8000/redoc | API reference | None (dev only) |
| OpenAPI spec | http://localhost:8000/openapi.json | Machine-readable | None |

### CORS configuration (api/main.py)

```
allow_origins: ["http://localhost:3000", "http://localhost:5173"]
allow_credentials: true
allow_methods: ["*"]
allow_headers: ["*"]
```

Port 3000 suggests React/Next.js dev server was anticipated.
Port 5173 suggests Vite (React/Vue/Svelte) dev server was anticipated.

## Proposed web app architecture

### Two-app strategy

| App | Purpose | Users | Priority |
|-----|---------|-------|----------|
| **Banxe Portal** (customer-facing) | Banking dashboard, payments, KYC, statements | Customers | P2 |
| **Banxe Ops Console** (internal) | MLRO dashboard, HITL queue, SAR, FIN060, recon | Staff | P1 |

### Recommended stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | Next.js 14+ (App Router) | SSR for SEO, API routes for BFF, TypeScript-first |
| UI library | shadcn/ui + Tailwind CSS | Production-grade components, accessible |
| Auth | Keycloak OIDC via next-auth | 7 roles already defined in realm |
| State | TanStack Query (React Query) | Server-state caching, optimistic updates |
| Forms | React Hook Form + Zod | Matches Pydantic validation patterns |
| Charts | Recharts or Tremor | Safeguarding/recon dashboards |
| Tables | TanStack Table | Customer lists, transaction history, SAR list |
| Real-time | WebSocket (future) or polling | Recon status, payment tracking |

### Ops Console — page structure

```
/                           → Dashboard (recon status, HITL queue count, SAR stats)
/hitl                       → HITL Review Queue (GET /v1/hitl/queue)
/hitl/:caseId               → Case Detail + Decide (GET+POST /v1/hitl/queue/{id})
/sar                        → SAR List (GET /v1/reporting/sar)
/sar/new                    → File SAR (POST /v1/reporting/sar)
/sar/:sarId                 → SAR Detail (GET /v1/reporting/sar/{id})
/sar/:sarId/approve         → Approve SAR (POST .../approve)
/fin060                     → FIN060 Dashboard (POST .../generate, .../submit)
/customers                  → Customer List (GET /v1/customers)
/customers/new              → Onboard Customer (POST /v1/customers)
/customers/:id              → Customer Profile (GET /v1/customers/{id})
/customers/:id/kyc          → KYC Workflow (POST /v1/kyc/workflows)
/fraud                      → Fraud Assessment (POST /v1/fraud/assess)
/consumer-duty              → Consumer Duty Overview
/consumer-duty/vulnerability → Vulnerability Assessment (POST .../vulnerability)
/consumer-duty/fair-value   → Fair Value Assessment (POST .../fair-value)
/notifications              → Notification Manager (POST .../send, GET .../preview)
/sanctions                  → Sanctions Rescreen (POST .../rescreen/high-risk)
/settings                   → System settings
```

### Customer Portal — page structure

```
/                           → Login (Keycloak OIDC redirect)
/dashboard                  → Account balances, recent transactions
/accounts/:id               → Account detail, balance (GET /v1/ledger/accounts/{id}/balance)
/send                       → Send payment flow (POST /v1/payments)
/send/confirm               → Payment confirmation
/send/status/:key           → Payment status (GET /v1/payments/{key})
/transactions               → Transaction history (GET /v1/payments)
/kyc                        → KYC onboarding (POST /v1/kyc/workflows)
/kyc/documents              → Document upload (POST .../documents)
/kyc/status                 → KYC status (GET /v1/kyc/workflows/{id})
/profile                    → Customer profile (GET /v1/customers/{id})
/notifications              → Notification inbox
/statements                 → Statement download (needs new endpoint)
```

## Backend readiness for web

### Ready (can build UI immediately)

| Feature | Endpoints | Notes |
|---------|-----------|-------|
| Customer CRUD | 4 endpoints | Full lifecycle |
| Payments | 3 endpoints | Mock adapter; real Modulr blocked on BT-001 |
| KYC workflows | 5 endpoints | Mock + Ballerine adapters |
| Ledger balances | 2 endpoints | Via Midaz CBS |
| HITL review | 5 endpoints | Full queue + decide flow |
| SAR management | 6 endpoints | Full lifecycle incl. approve/submit/withdraw |
| FIN060 | 2 endpoints | Generate + submit |
| Fraud check | 1 endpoint | Pre-payment gate |
| Consumer duty | 5 endpoints | Full PS22/9 coverage |
| Notifications | 3 endpoints | Send + preview + status |
| Health | 2 endpoints | Liveness + readiness |

### Not ready (needs new backend work)

| Feature | Missing | Effort | Priority |
|---------|---------|--------|----------|
| Account opening | POST /v1/accounts | MEDIUM | P1 |
| Recon dashboard | GET /v1/recon/status, /history | MEDIUM | P1 |
| FX rates | GET /v1/fx/rates | SMALL (proxy to Frankfurter) | P2 |
| Statement PDF | GET /v1/statements/{id} | SMALL (WeasyPrint exists) | P2 |
| WebSocket events | WS /v1/events | MEDIUM (RabbitMQ→WS bridge) | P2 |
| Audit export | POST /v1/audit/export | SMALL | P3 |
| Pagination | Cursor/offset on list endpoints | SMALL | P1 |
| Search/filter | Query params on list endpoints | SMALL | P1 |

## Auth integration plan

Keycloak realm `banxe` already has 7 roles. Web apps need:

1. OIDC Authorization Code flow with PKCE (public client)
2. next-auth Keycloak provider configuration
3. Role-based route guards mapping Keycloak roles → page access:

| Keycloak role | Ops Console pages | Customer Portal pages |
|---------------|-------------------|----------------------|
| ADMIN | All | — |
| MLRO | HITL, SAR, FIN060, sanctions | — |
| COMPLIANCE_OFFICER | HITL, KYC, consumer duty, fraud | — |
| CFO | FIN060, reports | — |
| FRAUD_ANALYST | Fraud, HITL | — |
| OPERATOR | Customers, notifications | — |
| CUSTOMER | — | All customer-facing pages |

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*

## EXTRACT Update — 2026-04-13 (FUNCTION 3)

### New: Safeguarding module (CASS 15) — web readiness

COMPONENT: CASS 15 Safeguarding Dashboard
SOURCE: src/safeguarding/ (new module, commit 6668d7d)
STATUS: ready — backend implemented, no UI yet
SCREEN TYPE: dashboard + list + detail
DATA MODEL: SafeguardingAccount (client_id, amount, currency, pool_type), Position (total_client_funds, total_safeguarded, breach_flag), BreachRecord (breach_id, amount, detected_at, resolved_at)
AUTH REQUIRED: yes — MLRO, CFO roles
COMPLIANCE FLAG: yes — CASS 15, FCA PS22/9
PRIORITY: MVP (P0 — FCA deadline)
NOTES: Safeguarding pool must show daily position vs. client e-money holdings. Breach alerts must surface immediately in Ops Console.

COMPONENT: Safeguarding Reconciliation View
SOURCE: services/settlement/ (tri-party recon engine, commit cabfb2f) + services/recon/
STATUS: ready — backend implemented, no UI yet
SCREEN TYPE: table + status
DATA MODEL: ReconciliationReport (date, matched, unmatched, breach_flag), TriPartyRecord (custodian, amount, reference)
AUTH REQUIRED: yes — MLRO, CFO, COMPLIANCE_OFFICER
COMPLIANCE FLAG: yes — CASS 7.15
PRIORITY: MVP (P1)
NOTES: Move /recon dashboard from 'Not ready' to 'Ready' — tri-party recon engine now DONE (GAP-010).

### Ops Console — additional pages (post-safeguarding)

```
/safeguarding          → Safeguarding Position Dashboard (GET /v1/safeguarding/position)
/safeguarding/accounts → Safeguarding Account List (GET /v1/safeguarding/accounts)
/safeguarding/breaches → Breach History (GET /v1/safeguarding/breaches)
/recon                 → Tri-Party Recon Dashboard (GET /v1/recon/status, /v1/recon/report)
/recon/history         → Reconciliation History (GET /v1/recon/history)
```

### Ready table additions (post-2026-04-13 TRACK)

| Feature | Endpoints | Notes |
|---------|-----------|-------|
| Safeguarding position | GET /v1/safeguarding/position | CASS 15 — new, MVP |
| Safeguarding accounts | GET/POST /v1/safeguarding/accounts | Pool management |
| Safeguarding breaches | GET /v1/safeguarding/breaches | Breach log |
| Recon dashboard | GET /v1/recon/status, /report | Was 'Not ready' — now DONE |

### Not ready — removed (resolved)

| Feature | Resolution |
|---------|------------|
| Recon dashboard | Tri-party recon engine DONE (GAP-010, commit cabfb2f) — move to Ready |

*Last updated: 2026-04-13 (FUNCTION 3 EXTRACT — Architecture Skill Orchestrator)*
