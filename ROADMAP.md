# ROADMAP — Banxe EMI Stack

> **Legend:** ✅ DONE | 🔄 IN PROGRESS | ⏳ PENDING | 🔒 BLOCKED (external dependency)

---

## Phase 1 — Core EMI Platform ✅ COMPLETE

867 тестов green, ruff clean, coverage ≥ 80%.

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
| 14 | HITL Feedback Loop (AI learns from CTIO) | IL-056 | ✅ | EU AI Act Art.14 | — |
| 15 | Notification Service (email/Telegram) | IL-047 | ✅ | — | — |
| 16 | Redis Velocity Tracker | IL-048 | ✅ | — | — |
| 17 | Consumer Duty PS22/9 | IL-050 | ✅ | PS22/9 | — |
| 18 | **Jube Fraud Rules Engine** | IL-057 | ✅ | MLR 2017 Reg.26 | — |
| 19 | **Ballerine KYC Workflow Definitions** | IL-058 | ✅ | MLR 2017 §18 | — |
| 20 | **Marble Case Management** | IL-059 | ⏳ | EU AI Act Art.14 | — |
| 21 | Modulr Payments API (live) | BT-001 | 🔒 | PSR 2017 | CEO: register modulrfinance.com/developer |
| 22 | Companies House KYB | BT-002 | 🔒 | MLR 2017 Reg.28 | `COMPANIES_HOUSE_API_KEY` |
| 23 | OpenCorporates KYB | BT-003 | 🔒 | — | `OPENCORPORATES_API_KEY` |
| 24 | Sardine.ai Fraud Scoring | BT-004 | 🔒 | — | `SARDINE_API_KEY` |

---

## Phase 3 — Advanced Compliance Reporting ✅ COMPLETE

| # | Feature | IL | Status | FCA ref |
|---|---------|-----|--------|---------|
| 11 | FIN060 Safeguarding Return API | IL-052 | ✅ | CASS 15.12.4R |
| 12 | SAR Auto-Filing (POCA 2002 s.330) | IL-052 | ✅ | POCA 2002 |
| 13 | Consumer Duty Annual Report | IL-050 | ✅ | PS22/9 |

---

## Phase 4 — Infrastructure & Deployment ✅ DEPLOYED

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 25 | Safeguarding Deploy to GMKtec | IL-043 | ✅ | systemd timer 07:00 UTC Mon-Fri, next: Thu 09:01 CEST |
| 26 | n8n Workflows (shortfall alert) | IL-043 | ✅ | Imported. TODO: set Telegram credentials → activate |
| 27 | Ballerine Deploy to GMKtec | IL-055 | ✅ | workflow-service :3000, backoffice :5137 |
| 28 | Keycloak Deploy | IL-039 | ✅ | :8180, realm banxe, 7 roles |

---

## GMKtec — Running Services (2026-04-09)

| Service | Port | Integrated | Next step |
|---------|------|-----------|-----------|
| Jube (fraud rules engine) | :5001 | ✅ JubeAdapter (FRAUD_ADAPTER=jube) | Jube password needed |
| Marble (transaction monitoring UI) | :5002/:5003 | ❌ | IL-059 |
| Ballerine workflow-service | :3000 | ✅ adapter + definitions | Run register-ballerine-workflows.sh |
| Ballerine backoffice | :5137 | ✅ | — |
| Midaz ledger | :8095 | ✅ | — |
| Keycloak | :8180 | ✅ | — |
| Redis | :6379 | ✅ | — |
| RabbitMQ | :3004 | ✅ | — |
| n8n | :5678 | ✅ | Set Telegram credentials |
| Mock ASPSP | :8888 | ✅ | — |

---

## Invariants (reference)

| Invariant | Rule | State |
|-----------|------|-------|
| I-01 | No float for money | ✅ Decimal strings only |
| I-02 | Hard-block jurisdictions | ✅ RU/BY/IR/KP/CU/MM/AF/VE |
| I-03 | FATF greylist → EDD | ✅ 23 countries |
| I-04 | EDD threshold £10k | ✅ pipeline + HITL |
| I-05 | Decimal strings in API | ✅ Pydantic validators |
| I-27 | HITL feedback supervised | ✅ PROPOSES only |
| I-28 | Execution discipline | ✅ QRAA + IL ledger |

---

## Test matrix (2026-04-09)

| Suite | Tests | Status |
|-------|-------|--------|
| **Full suite** | **934** | ✅ |
| Phase 2 HITL + Feedback Loop | 35 | ✅ IL-056 |
| IL-057 Jube adapter | 67 | ✅ IL-057 |
| Phase 1 core | 480 | ✅ |
| Phase 2 services | 234 | ✅ |
| Phase 3 reporting | 37 | ✅ |
| Infra stubs | 29 | ✅ |
| IL-054 PDF | 28 | ✅ |
| IL-055 Ballerine | 24 | ✅ |

---

*Last updated: 2026-04-09 by Claude Code.*
