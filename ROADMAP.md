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
| 20 | **Marble Case Management** | IL-059 | ✅ | EU AI Act Art.14 | — |
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
| Marble (transaction monitoring UI) | :5002/:5003 | ✅ MarbleAdapter (CASE_ADAPTER=marble) | MARBLE_API_KEY + MARBLE_INBOX_ID needed |
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
| **Full suite** | **995** | ✅ |
| Phase 2 HITL + Feedback Loop | 35 | ✅ IL-056 |
| IL-057 Jube adapter | 67 | ✅ IL-057 |
| IL-059 Marble case management | 61 | ✅ IL-059 |
| Phase 1 core | 480 | ✅ |
| Phase 2 services | 234 | ✅ |
| Phase 3 reporting | 37 | ✅ |
| Infra stubs | 29 | ✅ |
| IL-054 PDF | 28 | ✅ |
| IL-055 Ballerine | 24 | ✅ |

---

---

## Phase 5 — Reconciliation + Breach Detection ✅ COMPLETE

| # | Feature | IL | Status | FCA ref |
|---|---------|-----|--------|----------|
| 29 | ASPSP Integration + MT940/CAMT.053 Parser | IL-015 | ✅ | CASS 15.3 |
| 30 | ClickHouse Production Schema + Grafana Dashboard | IL-015 | ✅ | CASS 15.12 |
| 31 | FCA RegData Auto-Submission + n8n Workflows | IL-015 | ✅ | CASS 15.12.4R |
| 32 | AI Agent Recon Analysis + Breach Prediction | IL-015 | ✅ | EU AI Act Art.14 |
| 33 | Grafana docker-compose + run_reconciliation MCP tool | IL-015 | ✅ | CASS 15.3 |

---

## Phase 6 — MCP Server + AI Infrastructure ✅ COMPLETE

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 34 | MCP Server (banxe_mcp) — FastMCP 28 tools | IL-MCP-01 | ✅ | Health, compliance, recon, AML |
| 35 | Semgrep SAST rules (banking) | IL-MCP-01 | ✅ | .semgrep/ |
| 36 | Soul prompt (system identity) | IL-MCP-01 | ✅ | .ai/soul.md |
| 37 | Orchestrator agent (swarm) | IL-MCP-01 | ✅ | agents/compliance/ |
| 38 | n8n workflow templates | IL-MCP-01 | ✅ | infra/n8n/ |
| 39 | Docker multi-service compose | IL-MCP-01 | ✅ | docker/ |
| 40 | Grafana provisioning (dashboards + datasources) | IL-MCP-01 | ✅ | infra/grafana/ |
| 41 | dbt models (compliance analytics) | IL-MCP-01 | ✅ | dbt/ |
| 42 | Infrastructure Utilization Canon | IL-MCP-01 | ✅ | .claude/rules/ |
| 43 | AI registries + API docs | IL-MCP-01 | ✅ | .ai/registries/ |

MCP Checklist: 28/28 tools ✅
Infrastructure Checklist: 15/15 ✅

---

## Phase 7 — UI/UX Open-Source Platform ⏳ PENDING

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 44 | Monorepo setup (pnpm + turbo) | IL-UI-01 | ⏳ | banxe-platform/ |
| 45 | Design system (tokens, atoms, molecules) | IL-UI-01 | ⏳ | packages/shared/ |
| 46 | Mobile app (Expo SDK 53 + NativeWind) | IL-UI-01 | ⏳ | packages/mobile/ |
| 47 | Web app (Next.js 15 + shadcn/ui) | IL-UI-01 | ⏳ | packages/web/ |
| 48 | PSD2 SCA flows + KYC screens | IL-UI-01 | ⏳ | Compliance UI |
| 49 | CLAUDE.md per package | IL-UI-01 | ⏳ | Multi-agent ready |
| 50 | .ai/registries/ (12 files) + .ai/reports/ (5 files) | IL-UI-01 | ⏳ | Intelligence layer |


## Phase 8 — Agent Routing Layer ⏳ PENDING

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 51 | Agent Gateway + Tier Workers | IL-ARL-01 | ⏳ | services/agent_routing/ |
| 52 | Playbook Engine (YAML routing rules) | IL-ARL-01 | ⏳ | config/playbooks/ |
| 53 | ReasoningBank (vector store + case memory) | IL-ARL-01 | ⏳ | services/reasoning_bank/ |
| 54 | Swarm Orchestrator (star/hierarchy/ring) | IL-ARL-01 | ⏳ | services/swarm/ |
| 55 | Specialized Agents (5 agents) | IL-ARL-01 | ⏳ | services/swarm/agents/ |
| 56 | Telemetry + Policy Engine | IL-ARL-01 | ⏳ | ClickHouse + Grafana |
| 57 | MCP Tools (4 new tools) | IL-ARL-01 | ⏳ | banxe_mcp/tools/ |
| 58 | Agent Routing Tests (120+) | IL-ARL-01 | ⏳ | tests/test_agent_routing/ |
---

*Last updated: 2026-04-11 by Perplexity Computer + Claude Code.*

*Last updated: 2026-04-09 by Claude Code.*
