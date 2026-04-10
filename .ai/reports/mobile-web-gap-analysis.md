# Mobile & Web Gap Analysis — banxe-emi-stack
# Source: api/routers/, api/main.py, config/banxe_config.yaml, .ai/registries/ui-map.md
# Created: 2026-04-10 | Updated: 2026-04-10 (Phase 5 intelligence pass)
# Migration Phase: 5
# Purpose: Endpoint-to-screen mapping, coverage analysis, and gap identification

## Current state

banxe-emi-stack is backend-only. No web or mobile frontend exists.
42 API endpoints are production-ready (mock adapters for external providers).

### Existing external UIs (deployed on GMKtec, not part of this repo)

| UI | Port | Purpose | Covers |
|----|------|---------|--------|
| Ballerine Backoffice | :5137 | KYC case review | KYC ops |
| Marble Dashboard | :5002/:5003 | Transaction monitoring | AML ops |
| n8n Editor | :5678 | Workflow automation | Ops automation |
| Keycloak Admin | :8180 | IAM admin | Auth management |
| Swagger UI | :8000/docs | API explorer (auto-generated) | Dev testing |
| ReDoc | :8000/redoc | API reference (auto-generated) | Dev reference |

## Endpoint-to-screen mapping (all 42 endpoints)

### Customer-facing endpoints → screens

| # | Endpoint (full path) | Method | Customer Portal screen | Mobile screen | Coverage |
|---|---------------------|--------|----------------------|---------------|----------|
| 1 | /v1/customers | POST | — (ops only) | — (ops only) | Ops only |
| 2 | /v1/customers | GET | — (ops only) | — (ops only) | Ops only |
| 3 | /v1/customers/{id} | GET | /profile (C-09) | Profile (C-09) | Web + Mobile |
| 4 | /v1/customers/{id}/lifecycle | POST | — (ops only) | — (ops only) | Ops only |
| 5 | /v1/payments | POST | /send (C-04) | Send Payment (C-04) | Web + Mobile |
| 6 | /v1/payments | GET | /transactions (C-06) | Transaction History (C-06) | Web + Mobile |
| 7 | /v1/payments/{idempotency_key} | GET | /send/status/:key (C-05) | Payment Status (C-05) | Web + Mobile |
| 8 | /v1/ledger/accounts | GET | /dashboard (C-02) | Dashboard (C-02) | Web + Mobile |
| 9 | /v1/ledger/accounts/{id}/balance | GET | /accounts/:id (C-03) | Account Detail (C-03) | Web + Mobile |
| 10 | /v1/kyc/workflows | POST | /kyc (C-07) | KYC Onboarding (C-07) | Web + Mobile |
| 11 | /v1/kyc/workflows/{id} | GET | /kyc/status (C-08) | KYC Status (C-08) | Web + Mobile |
| 12 | /v1/kyc/workflows/{id}/documents | POST | /kyc/documents (C-07) | Document Capture (C-07) | Web + Mobile |
| 13 | /v1/kyc/workflows/{id}/approve-edd | POST | — (ops only) | — (ops only) | Ops only |
| 14 | /v1/kyc/workflows/{id}/reject | POST | — (ops only) | — (ops only) | Ops only |
| 15 | /v1/fraud/assess | POST | (server-side pre-gate) | (server-side pre-gate) | Backend |
| 16 | /v1/notifications/send | POST | — (ops only) | — (ops only) | Ops only |
| 17 | /v1/notifications/{id}/status | GET | /notifications (C-10) | Notification Inbox (C-10) | Web + Mobile |
| 18 | /v1/notifications/preview | GET | — (ops only) | — (ops only) | Ops only |

### Internal/ops endpoints → screens

| # | Endpoint (full path) | Method | Ops Console screen | Coverage |
|---|---------------------|--------|-------------------|----------|
| 19 | /v1/hitl/queue | GET | /hitl (I-02) | Ops Console |
| 20 | /v1/hitl/queue | POST | /hitl (I-02) | Ops Console |
| 21 | /v1/hitl/queue/{case_id} | GET | /hitl/:caseId (I-03) | Ops Console |
| 22 | /v1/hitl/queue/{case_id}/decide | POST | /hitl/:caseId (I-03) | Ops Console |
| 23 | /v1/hitl/stats | GET | / dashboard (I-01) | Ops Console |
| 24 | /v1/reporting/fin060/generate | POST | /fin060 (I-06) | Ops Console |
| 25 | /v1/reporting/fin060/submit | POST | /fin060 (I-06) | Ops Console |
| 26 | /v1/reporting/sar | POST | /sar/new (I-04) | Ops Console |
| 27 | /v1/reporting/sar | GET | /sar (I-04) | Ops Console |
| 28 | /v1/reporting/sar/stats | GET | / dashboard (I-01) | Ops Console |
| 29 | /v1/reporting/sar/{sar_id} | GET | /sar/:sarId (I-04) | Ops Console |
| 30 | /v1/reporting/sar/{sar_id}/approve | POST | /sar/:sarId/approve (I-05) | Ops Console |
| 31 | /v1/reporting/sar/{sar_id}/submit | POST | /sar/:sarId (I-05) | Ops Console |
| 32 | /v1/reporting/sar/{sar_id}/withdraw | POST | /sar/:sarId (I-05) | Ops Console |
| 33 | /v1/consumer-duty/vulnerability | POST | /consumer-duty/vulnerability (I-11) | Ops Console |
| 34 | /v1/consumer-duty/vulnerability/{customer_id} | GET | /consumer-duty/vulnerability (I-12) | Ops Console |
| 35 | /v1/consumer-duty/fair-value | POST | /consumer-duty/fair-value (I-11) | Ops Console |
| 36 | /v1/consumer-duty/outcomes | POST | /consumer-duty (I-11) | Ops Console |
| 37 | /v1/consumer-duty/report | POST | /consumer-duty (I-11) | Ops Console |

### System/internal endpoints (no UI screen needed)

| # | Endpoint (full path) | Method | Purpose | UI needed |
|---|---------------------|--------|---------|-----------|
| 38 | /health | GET | Liveness check | No — monitoring tools |
| 39 | /health/ready | GET | Readiness check | No — monitoring tools |
| 40 | /webhooks/watchman | POST | Watchman list update webhook | No — inbound webhook |
| 41 | /internal/notifications/mlro | POST | MLRO alert trigger | No — called by agents (I-14 optional) |
| 42 | /compliance/sanctions/rescreen/high-risk | POST | Sanctions rescreen trigger | No — MLRO tool (I-15 optional) |

## Coverage summary

| Category | Total endpoints | Covered by web | Covered by mobile | Ops-only | System/no-UI |
|----------|----------------|----------------|-------------------|----------|-------------|
| Customers | 4 | 1 (GET by ID) | 1 (GET by ID) | 3 (CRUD, lifecycle) | 0 |
| Payments | 3 | 3 | 3 | 0 | 0 |
| Ledger | 2 | 2 | 2 | 0 | 0 |
| KYC | 5 | 3 (start, docs, status) | 3 (start, docs, status) | 2 (approve-edd, reject) | 0 |
| Fraud | 1 | 0 (backend pre-gate) | 0 (backend pre-gate) | 0 | 1 |
| HITL | 5 | 0 | 0 | 5 | 0 |
| Reporting | 9 | 0 | 0 | 9 | 0 |
| Consumer Duty | 5 | 0 | 0 | 5 | 0 |
| Notifications | 3 | 1 (status) | 1 (status) | 2 (send, preview) | 0 |
| MLRO alerts | 1 | 0 | 0 | 0 | 1 |
| Sanctions | 1 | 0 | 0 | 0 | 1 |
| Health | 2 | 0 | 0 | 0 | 2 |
| Webhooks | 1 | 0 | 0 | 0 | 1 |
| **Total** | **42** | **10** | **10** | **26** | **6** |

### Coverage rates

- Customer portal: 10/42 endpoints (24%) — correct, only customer-facing subset needed
- Mobile app: 10/42 endpoints (24%) — mirrors customer portal (subset + mobile-specific UX)
- Ops console: 26/42 endpoints (62%) — all internal/operational endpoints
- System (no UI): 6/42 endpoints (14%) — health, webhooks, agent triggers
- Total coverage: 42/42 (100%) — every endpoint is mapped to a destination

## Gap analysis

### Web gaps (no existing endpoint — need new backend work)

| Gap ID | Gap | Needed for | Proposed endpoint | Priority | Effort |
|--------|-----|-----------|-------------------|----------|--------|
| W-01 | Account opening flow | Customer onboarding | POST /v1/accounts | P1 | MEDIUM |
| W-02 | Safeguarding recon dashboard | Ops console home | GET /v1/recon/status, GET /v1/recon/history | P1 | MEDIUM |
| W-03 | Statement PDF download | Customer statements page | GET /v1/statements/{account_id} | P2 | SMALL |
| W-04 | FX rate display | Payment send flow | GET /v1/fx/rates?from=GBP&to=EUR | P2 | SMALL |
| W-05 | WebSocket real-time events | Payment tracking, recon status | WS /v1/events | P2 | MEDIUM |
| W-06 | Audit export trigger | Ops console | POST /v1/audit/export | P3 | SMALL |
| W-07 | List endpoint pagination | All list views | Cursor/offset params on GET endpoints | P1 | SMALL |
| W-08 | Search and filter params | Customer list, transaction list | Query params on GET endpoints | P1 | SMALL |

### Mobile-specific gaps (beyond web gaps)

| Gap ID | Gap | Impact | Priority | Effort |
|--------|-----|--------|----------|--------|
| M-01 | Push notification backend | No push — only email/SMS/Telegram today | P1 | MEDIUM |
| M-02 | Biometric token refresh | Keycloak refresh_token + device biometric | P1 | MEDIUM |
| M-03 | Device fingerprinting | Sardine.ai blocked on BT-004 | Blocked | — |
| M-04 | Per-device rate limiting | No device-based throttling | P2 | MEDIUM |
| M-05 | Offline mode / caching | API-only design has no offline support | P3 | LARGE |
| M-06 | Deep link schema | No app-to-app payment links | P3 | SMALL |

### Blocked items (external dependency)

| Blocker | Affects | Status | Provider |
|---------|---------|--------|----------|
| BT-001 | Live payments (web + mobile) | API key pending | Modulr |
| BT-004 | KYC real verification | API key pending | Sumsub |
| BT-005 | KYB company lookups | API key pending | Companies House |
| BT-009 | Fraud scoring (real) | API key pending | Sardine.ai |

## Priority roadmap

### Phase 1 — Ops Console (P1) — estimated 6-8 weeks

Build internal operations dashboard consuming 26 ops-only endpoints.
Unblocked — all endpoints work with mock adapters.

Required new backend:
- GET /v1/recon/status and /history (W-02)
- Pagination on list endpoints (W-07)
- Search/filter params (W-08)

### Phase 2 — Customer Portal (P2) — estimated 8-12 weeks

Build customer-facing web app consuming 10 customer endpoints.
Partially blocked — real payments need BT-001.

Required new backend:
- POST /v1/accounts (W-01)
- GET /v1/statements/{id} (W-03)
- GET /v1/fx/rates (W-04)
- WS /v1/events (W-05)

### Phase 3 — Mobile App (P3) — estimated 13-19 weeks

Build customer-facing mobile app sharing API with web portal.
Blocked on: Phase 2 complete, BT-001 live, push notification backend.

Required new backend:
- Push notification service (M-01)
- Biometric token flow (M-02)
- Per-device rate limiting (M-04)

## Recommendations

1. [FACT] All 42 existing endpoints are mapped — 100% coverage across ops console, customer portal, mobile, and system categories
2. [FACT] 8 new web endpoints and 6 mobile-specific backend features are needed
3. [CONCLUSION] Ops console can be built immediately — zero external blockers, all 26 endpoints work with mock adapters
4. [CONCLUSION] Customer portal is partially viable now — 10 endpoints work but real payments blocked on BT-001
5. [CONCLUSION] Mobile app should wait for web portal completion — shared API patterns reduce duplication

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*
