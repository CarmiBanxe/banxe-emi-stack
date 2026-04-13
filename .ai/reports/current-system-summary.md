# Current System Summary — banxe-emi-stack
# Source: FUNCTION 1 full scan (Architecture Skill Orchestrator) + Sprint 12 update
# Updated: 2026-04-13 (Sprint 12: CASS 15 safeguarding API + tri-party recon)
# Branch: main

---

## What is this system?

**Banxe AI Bank** is an FCA-authorised Electronic Money Institution (EMI) backend platform built with FastAPI/Python. It provides the full compliance and banking infrastructure for an e-money issuer operating under UK FCA regulation (CASS, PS23/3, EMR 2011, Consumer Duty PS22/9).

---

## What is built and working today

### APIs — 78 endpoints across 21 routers (Sprint 12)

| Domain | Endpoints | Status |
|--------|-----------|--------|
| Fraud & AML assessment | POST /v1/fraud/assess | ACTIVE |
| KYC workflows | 5 endpoints /v1/kyc/* | ACTIVE |
| Payments (FPS/SEPA) | 3 endpoints /v1/payments/* | ACTIVE |
| Customer management | 4 endpoints /v1/customers/* | ACTIVE |
| SAR filing + MLRO | 7 endpoints /v1/reporting/sar/* | ACTIVE |
| FIN060 regulatory | 2 endpoints /v1/reporting/fin060/* | ACTIVE (PDF) / STUB (submit) |
| HITL queue | 5 endpoints /v1/hitl/* | ACTIVE |
| Notifications | 3 endpoints /v1/notifications/* | ACTIVE |
| Ledger balances | 2 endpoints /v1/ledger/* | STUB |
| Consumer duty | 5 endpoints /v1/consumer-duty/* | ACTIVE |
| Sanctions rescreen | POST /compliance/sanctions/high-risk | ACTIVE |
| Watchman webhook | POST /webhooks/watchman | ACTIVE |
| MLRO notifications | POST /internal/notifications/mlro | ACTIVE |
| Health | GET /health, /health/ready | ACTIVE |
| Auth (JWT) | POST /v1/auth/login | ACTIVE |
| Statements | 2 endpoints /v1/accounts/*/statement | ACTIVE |
| Compliance KB (RAG) | 8 endpoints /v1/kb/* | ACTIVE |
| Experiments (A/B) | 8 endpoints /v1/experiments/* | ACTIVE |
| Transaction Monitor | 8 endpoints /v1/monitor/* | ACTIVE |
| **Safeguarding CASS 15** | **6 endpoints /v1/safeguarding/*** | **ACTIVE (sandbox)** |
| **Reconciliation CASS 7.15** | **3 endpoints /v1/recon/*** | **ACTIVE (sandbox)** |

### Business logic

- **AML:** Transaction monitoring (velocity in Redis or in-memory), SAR lifecycle (file → approve → submit), thresholds
- **Fraud:** FraudAML pipeline with Jube (self-hosted ML, gmktec:5001) or mock; PSR APP 2024 compliant
- **KYC:** Full workflow lifecycle (create → documents → EDD → approve/reject); mock + Balleryne adapters
- **HITL:** Review queue with SLA timers (SAR 24h, EDD 4h, sanctions reversal 1h); OrgRoleChecker for MLRO/CEO gates
- **Payments:** FPS + SEPA CT + SEPA Instant via Modulr sandbox; webhook signature verification
- **Reconciliation:** CASS 7.15 daily recon from CAMT.053 (mock-ASPSP); breach detection with n8n alerting
- **Reporting:** FIN060 PDF via WeasyPrint; RegData submission (stub)
- **Consumer Duty:** PS22/9 vulnerability + fair value assessment
- **Events:** RabbitMQ pub/sub for cross-service communication (mock in tests)

### Compliance architecture

- All monetary amounts: string (never float) — I-05 invariant enforced throughout
- No PII in logs — I-09 invariant enforced
- 5-year audit trail in ClickHouse (append-only)
- HITL mandatory for: SAR filing, EDD onboarding, sanctions reversal, PEP onboarding
- OrgRoleChecker enforces MLRO / CEO / BOARD role gates
- 10 custom semgrep rules enforce security invariants on every commit

### AI compliance agents (swarm — scaffold phase)

7 agents defined in `agents/compliance/swarm.yaml`:
- `mlro_agent` (coordinator, L2 autonomy)
- `aml_check_agent`, `tm_agent`, `fraud_detection_agent`, `jube_adapter_agent` (Layer 2, L3)
- `sanctions_check_agent`, `cdd_review_agent` (Layer 1, L3)

**Status:** YAML scaffold + soul files complete. Claude AI tool-calling bridge to services: NOT YET IMPLEMENTED.
Compliance KB active: 476 chunks / 16 domains (ChromaDB + all-MiniLM-L6-v2).

### Testing

- 57+ test files | 2,227 tests | 80.92%+ coverage (threshold: 80%)
- Pre-commit: ruff + biome + bandit + mypy (src/) + semgrep + pytest-fast
- CI quality-gate.yml: gitleaks + ruff + biome + mypy + pytest (80% gate) + semgrep + vitest
- Coverage scope: `services + api + src` (aligned pre-commit ↔ CI)

---

## What is NOT working (stubs / blocked)

| Item | Status | Blocker |
|------|--------|---------|
| Sardine fraud scoring | STUB | CEO: SARDINE_CLIENT_ID + SARDINE_SECRET_KEY |
| Modulr live API | STUB | CEO: register modulrfinance.com/developer |
| Companies House KYB | STUB | Ops: COMPANIES_HOUSE_API_KEY |
| OpenCorporates KYB | STUB | Ops: OPENCORPORATES_API_KEY |
| Marble case management | STUB | Ops: MARBLE_API_KEY |
| Keycloak IAM | STUB | Deploy: Keycloak on gmktec:8180 |
| Midaz ledger (CBS) | STUB | Deploy: Midaz on localhost:8095 + MIDAZ_TOKEN |
| NCA SAROnline submission | STUB | Dev: NCA API integration not implemented |
| FCA RegData real submission | STUB | Dev: FCA portal integration pending |
| ClickHouse persistence | PARTIAL | Schema not fully initialized |
| AI agent autonomy | SCAFFOLD | Claude AI tool-calling not wired to services |
| PSD2 real ASPSP | STUB | Mock ASPSP in use; real bank integration pending |

---

## Architecture design patterns

1. **Hexagonal (Ports & Adapters):** `*_port.py` = Protocol; `*_adapter.py` = implementation; swappable via env vars
2. **In-Memory first, swap to real:** Default is mock/in-memory; production = credentials provisioning
3. **HITL gates:** OrgRoleChecker enforces role-based approval (MLRO/CEO/BOARD)
4. **Event-driven:** RabbitMQ pub/sub; n8n for MLRO alerts
5. **Audit-first:** All decisions → ClickHouse append-only trail
6. **No floats for money:** All amounts as str/Decimal throughout

---

## Critical path to 7 May 2026 (CASS compliance deadline)

| Item | Status | Priority |
|------|--------|----------|
| CASS 7.15 daily recon (mock-ASPSP) | ✅ ACTIVE | P0 done |
| FIN060 PDF generation | ✅ ACTIVE | P0 done |
| pgAudit on PostgreSQL | ✅ ACTIVE | P0 done |
| Frankfurter FX (self-hosted) | ✅ ACTIVE | P0 done |
| mock-ASPSP PSD2 gateway | ✅ ACTIVE | P0 done |
| Modulr live API key | 🔒 BLOCKED/CEO | P0 pending |
| ClickHouse schema init | ⚠️ PARTIAL | P0 pending |
| FCA RegData real submission | 🔒 STUB | P0 pending |
| Keycloak deploy (auth) | 🔒 STUB | P1 |

---

## Open questions

1. **api/deps.py auth resolver:** Keycloak OIDC integration may have gaps between stub and live — not fully scanned
2. **RabbitMQ in production:** Test suite uses mock event bus; production event routing not integration-tested
3. **NCA SAROnline:** No implementation path — requires NCA API credentials + legal review
4. **AI agents ↔ services:** Tool-calling bridge between swarm.yaml agents and actual service methods not implemented
5. **ClickHouse schema:** Driver installed, audit trail referenced in services, but schema init SQL not found in scan

---

### Sprint 12 deliverables (2026-04-13)

- `src/products/emi_products.py` — EMI product catalogue (GAP-014): 4 products, all safeguarded, Consumer Duty FairValueAssessment
- `src/api/gateway.py` — API gateway (GAP-023): auth, sliding-window rate-limiting, idempotency (SHA-256, 24h TTL)
- `api/routers/safeguarding.py` — 6 CASS 15 endpoints; wires SafeguardingAgent + FIN060Generator
- `api/routers/recon.py` — 3 tri-party recon endpoints; wires TriPartyReconciler with sandbox stubs
- Tests: 212 new tests across 6 new test files (test_api_safeguarding, test_api_recon, test_src_billing, test_src_safeguarding_agent, test_src_products, test_src_api)
- Quality pipeline: coverage gate 79.82% → 80.92%; mypy added; Bandit High 0

---

*Updated: Architecture Skill Orchestrator FUNCTION 1 | Sprint 12 | 2026-04-13*
