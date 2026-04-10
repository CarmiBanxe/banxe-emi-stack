# Product Map — banxe-emi-stack
# Source: FUNCTION 2 (FIX) — Architecture Skill Orchestrator, based on FUNCTION 1 scan
# Created: 2026-04-10 | Updated: 2026-04-10 | Version: 2.0 (post-Phase 6)
# Purpose: Living product architecture map — modules, API surface, agents, readiness

## Product Overview

**Banxe AI Bank** — FCA-authorised Electronic Money Institution (EMI), UK.
Python 3.12 / FastAPI 0.111+ / Pydantic v2 / Hexagonal Architecture.
Primary regulation: FCA CASS 15 / CASS 7.15 / MLR 2017 / PSR APP 2024.
Hard deadline: **7 May 2026** (CASS safeguarding compliance).
Product types: EMI Account, Business Account, FX Account, Prepaid Card.

---

## Modules

| Module | Domain | Status | API | Web Ready | Mobile Ready |
|--------|--------|--------|-----|-----------|--------------|
| `services/aml/` | AML/Compliance | ACTIVE | Via /v1/reporting/sar | Yes (SAR dashboard) | Partial |
| `services/fraud/` | Fraud/PSR | ACTIVE+STUB | /v1/fraud/assess | Yes | Yes |
| `services/kyc/` | KYC | ACTIVE+STUB | /v1/kyc/* (5) | Yes (onboarding flow) | Yes (EDD mobile) |
| `services/hitl/` | Compliance Gate | ACTIVE | /v1/hitl/* (5) | Yes (MLRO dashboard) | Partial |
| `services/payment/` | Transactions | ACTIVE+STUB | /v1/payments/* (3) | Yes | Yes |
| `services/notifications/` | Infra | ACTIVE | /v1/notifications/* (3) | No (backend only) | No |
| `services/customer/` | Banking Core | ACTIVE | /v1/customers/* (4) | Yes | Yes |
| `services/ledger/` | Banking Core | STUB | /v1/ledger/* (2) | Yes (balance screen) | Yes |
| `services/recon/` | Banking Core | ACTIVE+STUB | — (internal cron) | Partial (ops console) | No |
| `services/reporting/` | Reporting | ACTIVE+STUB | /v1/reporting/fin060/* | Yes (compliance ops) | No |
| `services/case_management/` | Compliance | STUB | — (internal) | No | No |
| `services/iam/` | Infra | STUB | — (via Keycloak) | Yes (SSO) | Yes (OAuth2) |
| `services/events/` | Infra | ACTIVE | — (internal) | No | No |
| `services/config/` | Infra | ACTIVE | — (internal) | No | No |
| `services/consumer_duty/` | Compliance | ACTIVE | /v1/consumer-duty/* (5) | Yes (ops console) | No |
| `services/complaints/` | Compliance | ACTIVE | — (n8n webhook) | No | No |
| `services/auth/` | Infra | ACTIVE | — (2FA flows) | Yes | Yes (biometric 2FA) |
| `services/statements/` | Banking Core | ACTIVE | — (internal) | Yes (statement download) | Yes |
| `services/resolution/` | Compliance | ACTIVE | — (internal) | No | No |
| `services/webhooks/` | Infra | ACTIVE | /webhooks/*, /internal/* | No | No |
| `services/providers/` | Infra | ACTIVE | — (factory) | No | No |
| `services/agreement/` | Banking Core | STUB | — | Yes (T&C acceptance) | Yes |

---

## Data Layer

| Model | Purpose | Key fields | Web | Mobile |
|-------|---------|-----------|-----|--------|
| `CustomerProfile` | Customer record | entity_type, lifecycle_state, risk_level, kyc_status | Yes — customer list/detail | Yes |
| `IndividualProfile` | Individual customer | first_name, last_name, dob, nationality, address | Yes — onboarding form | Yes |
| `CompanyProfile` | Business customer | company_name, registration_number, ubo_list | Yes — KYB form | Partial |
| `PaymentIntent` | Payment request | rail, amount (str), currency, debtor/creditor_account | Yes — payment form | Yes |
| `PaymentResult` | Payment outcome | payment_id, status, amount, created_at | Yes — transaction history | Yes |
| `SARReport` | SAR filing | sar_id, status, reasons, mlro_reviewed_by, nca_reference | Yes — MLRO console | No |
| `ReviewCase` | HITL case | case_id, status, expires_at, hours_remaining | Yes — HITL dashboard | No |
| `FraudScoringResult` | Fraud decision | decision, fraud_risk, aml_edd_required, requires_hitl | No (internal) | No |
| `KYCWorkflowResult` | KYC status | workflow_id, status, kyc_type, rejection_reason | Yes — onboarding status | Yes |
| `FIN060Data` | Regulatory report | period, avg_daily_client_funds, capital_requirement | Yes — compliance console | No |
| `MonitorResult` | AML monitoring | score, alert_level, typology_matches | No (internal) | No |
| `NotificationRequest` | Notification | channel, type, recipient, template | No (backend) | No |

---

## API Surface

### Public (customer-facing)
```
POST /v1/customers                        — Create customer (onboarding)
GET  /v1/customers/{id}                   — Get customer profile
POST /v1/customers/{id}/lifecycle         — Lifecycle transitions (activate/suspend)
POST /v1/kyc/workflows                    — Start KYC verification
GET  /v1/kyc/workflows/{id}               — KYC status polling
POST /v1/kyc/workflows/{id}/documents     — Submit documents
GET  /v1/payments/{idempotency_key}       — Payment status
GET  /v1/ledger/accounts/{id}/balance     — Account balance
```

### Operations (MLRO/compliance dashboard)
```
POST /v1/payments                         — Initiate payment (FPS/SEPA)
POST /v1/fraud/assess                     — Fraud + AML assessment
POST /v1/reporting/sar                    — File SAR
GET  /v1/reporting/sar                    — List SARs
POST /v1/reporting/sar/{id}/approve       — MLRO approves SAR
POST /v1/reporting/sar/{id}/submit        — Submit to NCA (STUB)
POST /v1/reporting/sar/{id}/withdraw      — Withdraw SAR
GET  /v1/reporting/sar/stats              — SAR stats
GET  /v1/hitl/queue                       — Review queue
POST /v1/hitl/queue/{id}/decide           — MLRO decision
GET  /v1/hitl/stats                       — HITL stats
POST /v1/reporting/fin060/generate        — Generate FIN060 PDF
POST /v1/reporting/fin060/submit          — Submit to RegData (STUB)
POST /v1/consumer-duty/report             — Consumer duty annual report
POST /v1/kyc/workflows/{id}/approve-edd   — MLRO approves EDD
POST /v1/kyc/workflows/{id}/reject        — Reject KYC workflow
POST /compliance/sanctions/high-risk      — Trigger sanctions rescreen
```

### Internal / Webhooks
```
POST /webhooks/watchman                   — Watchman sanctions hit
POST /internal/notifications/mlro         — MLRO alert notification
GET  /health | /health/ready              — Health checks
```

---

## Agent Layer

| Agent | Role | Trigger | Tools | Status |
|-------|------|---------|-------|--------|
| `mlro_agent` | Coordinator (L2) | L2+ escalations, regulatory deadlines | SAR filing, threshold changes, sanctions | SCAFFOLD |
| `jube_adapter_agent` | Fraud scoring (L3) | Every transaction | Jube ML API | SCAFFOLD |
| `sanctions_check_agent` | Screening (L3) | Onboarding, periodic | Watchman API | SCAFFOLD |
| `aml_check_agent` | AML triage (L3) | TM alerts, Jube scores | hitl_check_gate, sar_service | SCAFFOLD |
| `tm_agent` | TX monitoring (L3) | Real-time TX events | clickhouse_log, n8n_trigger | SCAFFOLD |
| `cdd_review_agent` | CDD (L2) | Onboarding, periodic | sanctions_check, hitl_gate | SCAFFOLD |
| `fraud_detection_agent` | Fraud (L3) | High-risk TX | marble_create_case, mlro_notify | SCAFFOLD |

**Knowledge Base:** ChromaDB, 476 chunks, 16 compliance domains.
**Bridge to services:** NOT YET IMPLEMENTED — tool-calling wiring is next major milestone.

---

## Integration Map

| External Service | Role | Data flow | Status |
|-----------------|------|-----------|--------|
| Jube (gmktec:5001) | Fraud ML scoring | TX → score (0-100) | ACTIVE |
| Modulr (sandbox) | Payment rails | FPS/SEPA submission + webhook | ACTIVE |
| Watchman (moov) | Sanctions screening | Inbound webhook on hit | STUB |
| Balleryne (gmktec:3000) | KYC EDD | Workflow create/approve | STUB |
| Marble (checkmarble.com) | Case management | Case creation on alert | STUB |
| Keycloak (gmktec:8180) | IAM / SSO | Token validation | STUB |
| Midaz (localhost:8095) | Core Banking Ledger | Balance queries | STUB |
| SendGrid | Email notifications | MLRO alerts, customer comms | ACTIVE |
| n8n (localhost:5678) | Workflow automation | MLRO alert workflows | ACTIVE |
| Frankfurter (localhost:8181) | FX rates (ECB) | FX pricing | ACTIVE |
| ClickHouse | Audit trail | Append-only 5-year log | PARTIAL |
| ChromaDB | Compliance KB | RAG for agent queries | ACTIVE |
| mock-ASPSP (localhost:8888) | PSD2 bank statements | CAMT.053 polling | ACTIVE (mock) |

---

## Web Readiness (Operations Console — React/Next.js)

| Feature | Source | Status | Priority |
|---------|--------|--------|----------|
| Customer list + detail | GET /v1/customers | Ready | MVP |
| Customer onboarding form | POST /v1/customers + /v1/kyc/workflows | Ready | MVP |
| KYC status tracking | GET /v1/kyc/workflows/{id} | Ready | MVP |
| Payment initiation | POST /v1/payments | Ready | MVP |
| Transaction history | GET /v1/payments | Ready | MVP |
| Account balance | GET /v1/ledger/accounts/{id}/balance | STUB backend | MVP (blocked) |
| HITL review queue | GET/POST /v1/hitl/queue | Ready | MVP |
| SAR management | /v1/reporting/sar/* | Ready | MVP |
| MLRO dashboard | /v1/hitl/*, /v1/reporting/sar/* | Ready | MVP |
| FIN060 PDF download | POST /v1/reporting/fin060/generate | Ready | P1 |
| Consumer duty report | POST /v1/consumer-duty/report | Ready | P1 |
| Fraud assessment view | Internal (no direct endpoint) | Needs endpoint | P1 |
| Sanctions rescreen | POST /compliance/sanctions/high-risk | Ready | P1 |

**Missing for web MVP:** Account balance (Midaz STUB), login/SSO (Keycloak STUB), WebSocket for real-time HITL alerts

## Mobile Readiness (React Native / Expo)

| Feature | Source | Status | Priority |
|---------|--------|--------|----------|
| Customer onboarding flow | POST /v1/customers + /v1/kyc | Ready | MVP |
| KYC document upload | POST /v1/kyc/workflows/{id}/documents | Ready | MVP |
| Payment send (FPS/SEPA) | POST /v1/payments | Ready | MVP |
| Payment status poll | GET /v1/payments/{key} | Ready | MVP |
| Account balance | GET /v1/ledger/accounts/{id}/balance | STUB backend | MVP (blocked) |
| 2FA authentication | services/auth (internal) | Ready (backend) | MVP |
| Push notifications | SendGrid → needs push adapter | Missing | P1 |
| Statement download | services/statements | No endpoint yet | P1 |
| PSD2 consent screen | Not implemented | Missing | P1 |
| Biometric auth | Not implemented | Missing | P1 |

**Missing for mobile MVP:** Push notification adapter, statement endpoint, biometric auth, PSD2 consent screen, Keycloak mobile OAuth2 flow

---

## Phase Completion

| Phase | Name | Status | Tests | Key deliverable |
|-------|------|--------|-------|-----------------|
| Phase 1 | Core EMI Platform | ✅ COMPLETE | 867 | 13 features: safeguarding, recon, payments, KYC, AML, IAM, API |
| Phase 2 | Compliance Intelligence | 🔄 IN PROGRESS | — | HITL, Jube, Marble, Balleryne — 4 items BLOCKED |
| Phase 3 | Advanced Compliance Reporting | ✅ COMPLETE | — | FIN060, SAR auto-filing, consumer duty |
| Phase 4 | Infrastructure & Deployment | ✅ DEPLOYED | — | GMKtec, systemd, n8n, Keycloak scaffold |
| Phase 5–6 | Claude AI Scaffold | ✅ COMPLETE | 1,102 | .claude/ rules, .ai/ registries, Prompt 1-3 |

## Blocked items (external dependencies)

| # | Item | Blocker | Owner | Status |
|---|------|---------|-------|--------|
| BT-001 | Modulr Payments API (live) | CEO: register modulrfinance.com/developer | CEO | 🔒 |
| BT-002 | Companies House KYB | COMPANIES_HOUSE_API_KEY | Ops | 🔒 |
| BT-003 | OpenCorporates KYB | OPENCORPORATES_API_KEY | Ops | 🔒 |
| BT-004 | Sardine.ai Fraud Scoring | SARDINE_CLIENT_ID + SARDINE_SECRET_KEY | CEO | 🔒 |
| BT-005 | Marble Case Management | MARBLE_API_KEY | Ops | 🔒 |

## Products (from config/banxe_config.yaml)

| Product | Currencies | Status | Key fees |
|---------|------------|--------|----------|
| EMI Account | GBP, EUR, USD | Active | FPS £0.20, SEPA CT €0.50, FX 0.25% |
| Business Account | GBP, EUR, USD, CHF | Active | FPS £0.30, SEPA CT €1.00, FX 0.20% |
| FX Account | GBP, EUR, USD, CHF, JPY, CAD, AUD, SGD | Active | FX 0.15% |
| Prepaid Card | GBP, EUR | Active | Card FX 2%, FPS top-up free |

## Transaction limits

| Product | Single TX | Daily | Monthly |
|---------|-----------|-------|---------|
| EMI Account | £50,000 | £25,000 | £100,000 |
| Business Account | £100,000 | £50,000 | £200,000 |
| FX Account | £25,000 | £25,000 | £100,000 |
| Prepaid Card | £5,000 | £5,000 | £20,000 |

## Open Questions

1. **AI agents ↔ services bridge:** Tool-calling wiring between swarm.yaml and actual service methods — not yet implemented. This is the next major milestone for AI agent autonomy.
2. **Web/mobile frontend:** No frontend codebase exists yet. Both web (React/Next.js) and mobile (React Native/Expo) are greenfield.
3. **Statement mobile endpoint:** `services/statements/` has logic but no exposed API endpoint — needed for mobile MVP.
4. **Push notifications:** SendGrid only; mobile push (FCM/APNS) adapter missing.
5. **ClickHouse schema init:** Driver and audit trail code exist, schema SQL not confirmed — needs verification before go-live.
6. **NCA SAROnline:** Submission is stub. No implementation path defined — requires NCA API + legal review.

## Improvement Suggestion (FUNCTION 4 — continuous improvement)

**Missing:** No `/v1/accounts/{id}/statement` endpoint for mobile statement download.
`services/statements/statement_service.py` exists (95% coverage) but is not wired to any router.
**Proposed:** Add `api/routers/statements.py` with `GET /v1/accounts/{id}/statement?from=&to=` → `StatementService`.
Mobile priority: MVP. Web priority: P1.
**Shall I implement it?**

---

*Version 2.0 | Generated by: Architecture Skill Orchestrator FUNCTION 2 (FIX) | 2026-04-10*
