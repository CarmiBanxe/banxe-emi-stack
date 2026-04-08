# ROADMAP — Banxe EMI Stack

> **Legend:** ✅ DONE | 🔄 IN PROGRESS | ⏳ PENDING | 🔒 BLOCKED (external dependency)

---

## Phase 1 — Core EMI Platform ✅ COMPLETE

All Phase 1 items delivered. 832 tests green, ruff clean, coverage ≥ 80%.

| # | Feature | IL | Status | FCA ref |
|---|---------|-----|--------|---------|
| 1 | FCA CASS 15 Safeguarding Engine | IL-001..011 | ✅ | CASS 15.12 |
| 2 | Reconciliation Engine (Midaz) | IL-012 | ✅ | CASS 15.3 |
| 3 | BreachDetector + FIN060 PDF | IL-015 | ✅ | CASS 15.12.4R |
| 4 | Payment / Webhook Service (Modulr stub) | IL-017 | ✅ | PSR 2017 |
| 5 | KYC / AML Pipeline (FraudAML) | IL-018..022 | ✅ | MLR 2017 Reg.28 |
| 6 | Customer Management Service | IL-023..025 | ✅ | GDPR Art.5 |
| 7 | Config-as-Data YAML | IL-040 | ✅ | — |
| 8 | Dual-Entity AML Thresholds | IL-041 | ✅ | MLR 2017 §33 |
| 9 | Keycloak IAM (7 roles, realm banxe) | IL-039 | ✅ | FCA PS3/19 |
| 10 | FastAPI REST API (80 endpoints) | IL-046 | ✅ | — |
| 11 | Infrastructure Stubs → Real (ClickHouse + PostgreSQL + RabbitMQ) | IL-053 | ✅ | — |
| 12 | PDF Statement Template (WeasyPrint) | IL-054 | ✅ | FCA PS7/24 |
| 13 | Ballerine KYC Adapter (self-hosted) | IL-055 | ✅ | MLR 2017 §18 |

---

## Phase 2 — Operations & Compliance Intelligence 🔄 IN PROGRESS

| # | Feature | IL | Status | FCA ref | Blocker |
|---|---------|-----|--------|---------|---------|
| 10 | **HITL Feedback Loop** (AI learns from CTIO) | IL-056 | 🔄 | EU AI Act Art.14 | None |
| 11 | Notification Service (email/Telegram) | IL-047 | ✅ | — | None |
| 12 | Redis Velocity Tracker | IL-048 | ✅ | — | None |
| 13 | Consumer Duty PS22/9 | IL-050 | ✅ | PS22/9 | None |
| 7 | Modulr Payments API (live) | BT-001 | 🔒 | PSR 2017 | CEO: register modulrfinance.com/developer |
| 8 | Companies House (KYB) | BT-002 | 🔒 | MLR 2017 Reg.28 | `COMPANIES_HOUSE_API_KEY` |
| 9 | OpenCorporates (KYB) | BT-003 | 🔒 | — | `OPENCORPORATES_API_KEY` |

---

## Phase 3 — Advanced Compliance Reporting ✅ COMPLETE

| # | Feature | IL | Status | FCA ref |
|---|---------|-----|--------|---------|
| 11 | FIN060 Safeguarding Return API | IL-052 | ✅ | CASS 15.12.4R |
| 12 | SAR Auto-Filing (POCA 2002 s.330) | IL-052 | ✅ | POCA 2002 |
| 13 | Consumer Duty Annual Report | IL-050 | ✅ | PS22/9 |

---

## Phase 4 — Infrastructure & Deployment ⏳ PLANNED

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 14 | Safeguarding Deploy to GMKtec | IL-043 | 🔒 | **CEO action required:** run `bash scripts/task1-safeguarding-deploy.sh` on GMKtec |
| 15 | n8n Workflows (regulatory alerts) | — | 🔒 | Waiting for GMKtec n8n password |
| 16 | Ballerine Deploy to GMKtec | IL-055 | ⏳ | `docker compose -f infra/ballerine/docker-compose.yml up` on GMKtec |
| 17 | Sardine.ai Fraud Scoring | BT-004 | 🔒 | `SARDINE_API_KEY` required |

---

## Invariants blocking NO feature (reference)

| Invariant | Rule | Current state |
|-----------|------|---------------|
| I-01 | No float for money | Enforced (Decimal strings) |
| I-02 | Hard-block jurisdictions | RU/BY/IR/KP/CU/MM/AF/VE |
| I-03 | FATF greylist → EDD | 23 countries |
| I-04 | EDD threshold £10k | Enforced in pipeline + HITL |
| I-05 | Decimal strings in API | Pydantic validators active |
| I-27 | HITL feedback loop supervised | feedback_loop.py PROPOSES only |
| I-28 | Execution discipline | QRAA + IL ledger |

---

## Test matrix (2026-04-09)

| Suite | Tests | Status |
|-------|-------|--------|
| Full suite | 832 | ✅ green |
| Phase 1 core | 480 | ✅ |
| Phase 2 services | 234 | ✅ |
| Phase 3 reporting | 37 | ✅ |
| Infra stubs | 29 | ✅ |
| IL-054 PDF | 28 | ✅ |
| IL-055 Ballerine | 24 | ✅ |

---

*Automatically updated by Claude Code. Last updated: 2026-04-09.*
