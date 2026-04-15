# ROADMAP — Banxe EMI Stack

> **Legend:** ✅ DONE | 🔄 IN PROGRESS | ⏳ PENDING | 🔒 BLOCKED (external dependency)

---

## Phase 1 — Core EMI Platform ✅ COMPLETE

2987 tests green, ruff clean, coverage 89.01%.

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

## Test matrix (2026-04-14 — Sprint 15)

| Suite | Tests | Status |
|-------|-------|--------|
| **Full suite** | **2700** | ✅ (87.00% coverage) |
| E2E integration tests | 19 | ✅ S14-02 |
| SCA challenge / verify | 17 | ✅ S15-01 |
| Token refresh (PSD2 RTS) | 8 | ✅ S15-05 |
| AML thresholds | 17 | ✅ S14-FIX-1 |
| Rule engine + velocity tracker | 17 | ✅ S14-FIX-1 |
| ReasoningBank + TOTP | 56 | ✅ S14-03 |
| Repo watch services | 35 | ✅ S14-03 |
| Markdown parser | 22 | ✅ S14-03 |
| Config modules | 21 | ✅ S14-03 |

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

## Phase 7 — UI/UX Open-Source Platform 🔄 IN PROGRESS

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 44 | Monorepo setup (pnpm + turbo) | IL-UI-01 | ✅ | banxe-platform/ — scaffold complete |
| 45 | Design system (tokens, atoms, molecules) | IL-UI-01 | ✅ | packages/shared/src/tokens/ — colors, typography, spacing, breakpoints |
| 46 | Mobile app (Expo SDK 53 + NativeWind) | IL-UI-01 | 🔄 | packages/mobile/ — scaffold done, SCA screen added |
| 47 | Web app (Next.js 15 + shadcn/ui) | IL-UI-01 | 🔄 | packages/web/ — scaffold done, SCAChallenge added |
| 48 | PSD2 SCA flows + KYC screens | IL-UI-01 | ✅ | SCA backend + web + mobile wired (S15-01/02/03) |
| 49 | CLAUDE.md per package | IL-UI-01 | ✅ | 4/4 (shared CLAUDE.md created S14-FIX-3) |
| 50 | .ai/registries/ (12 files) + .ai/reports/ (5 files) | IL-UI-01 | ✅ | 12 registries created (S14-09) |


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
| 58 | Agent Routing Tests 

## Phase 9 — Design-to-Code Pipeline PENDING

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 59 | Penpot self-hosted Docker | IL-D2C-01 | PENDING | infra/penpot/ |
| 60 | Penpot MCP Client | IL-D2C-01 | PENDING | services/design_pipeline/ |
| 61 | Design Token Pipeline | IL-D2C-01 | PENDING | config/design-tokens/ |
| 62 | AI Orchestrator FastAPI LangChain | IL-D2C-01 | PENDING | Penpot to code generation |
| 63 | Code Generator Mitosis | IL-D2C-01 | PENDING | React Vue RN output |
| 64 | Visual QA Agent | IL-D2C-01 | PENDING | BackstopJS Loki |
| 65 | BANXE UI Agents | IL-D2C-01 | PENDING | compliance txn report |
| 66 | D2C MCP Tools 4 tools | IL-D2C-01 | PENDING | banxe_mcp tools |
| 67 | D2C Tests 80 plus | IL-D2C-01 | PENDING | tests/test_design_pipeline/ |(120+) | IL-ARL-01 | ⏳ | tests/test_agent_routing/ |
---

*Last updated: 2026-04-14 by Claude Code + Moriel Carmi.*

*Last updated: 2026-04-09 by 

## Phase 10 — AI-Driven Design System ✅ COMPLETE

| # | Feature | IL | Status | Notes |
|---|---------|------|--------|-------|
| 68 | Design Token System (JSON + CSS) | IL-ADDS-01 | ✅ | src/design-system/tokens/ |
| 69 | Component Library (5 core components) | IL-ADDS-01 | ✅ | AlertPanel, Sidebar, StepWizard, ConsentToggle, AuditTrail |
| 70 | Dashboard Module UI | IL-ADDS-01 | ✅ | src/modules/dashboard/ |
| 71 | AML Monitor UI | IL-ADDS-01 | ✅ | src/modules/aml/ |
| 72 | KYC Wizard UI (5-step flow) | IL-ADDS-01 | ✅ | src/modules/kyc/ |
| 73 | Dark Mode + WCAG AA Compliance | IL-ADDS-01 | ✅ | Token switching |
| 74 | Storybook Component Docs | IL-ADDS-01 | ✅ | Visual documentation |
| 75 | Design System Tests (60+) | IL-ADDS-01 | ✅ | tests/design-system/ |

Tools: Google Stitch (free) + Ruflo (OSS) + OpenClaw (OSS) + Lucide React + Tailwind CSS

---

*Last updated: 2026-04-11 by 

## Phase 11 — Compliance AI Copilot ✅ DONE (Sprint 16 Block B — 2026-04-15)

| # | Feature | IL | Status | Notes |
|---|---------|------|--------|-------|
| 76 | Compliance Knowledge Base (ChromaDB + RAG) | IL-CKS-01 | ✅ | services/compliance_kb/ |
| 77 | MCP Knowledge Tools (6 tools) | IL-CKS-01 | ✅ | kb.query, kb.search, kb.compare_versions |
| 78 | Compliance Notebooks (EU-AML, UK-FCA, SOP, Cases) | IL-CKS-01 | ✅ | config/compliance_notebooks.yaml |
| 79 | Experiment Copilot (4 agents) | IL-CEC-01 | ✅ | designer, proposer, steward, reporter |
| 80 | AML Experiment Store (YAML + Git PR) | IL-CEC-01 | ✅ | compliance-experiments/ |
| 81 | MCP Experiment Tools (4 tools) | IL-CEC-01 | ✅ | experiment.design, experiment.propose_change |
| 82 | Realtime Transaction Monitor (ML + Rules) | IL-RTM-01 | ✅ | services/transaction_monitor/ |
| 83 | Explainable AML Alerts + KB Citations | IL-RTM-01 | ✅ | alerts/explanation_engine.py |
| 84 | MCP Monitor Tools (5 tools) | IL-RTM-01 | ✅ | monitor.score_transaction, monitor.get_alerts |
| 85 | Compliance AI Tests (284) | IL-CKS/CEC/RTM | ✅ | 88+91+105 tests — baseline 2987 total |

Total: 15 new MCP tools | 24 new API endpoints | 135+ new tests
All tools: ChromaDB + scikit-learn + SHAP + sentence-transformers (free/OSS)

---

*Last updated: 2026-04-11 by Perplexity Computer + Claude Code.*Perplexity Computer + Claude Code.*Claude Code.*


---

## Phase 12 — Customer Support Block ⏳ PENDING

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 86 | Chatwoot self-hosted (MIT) — live chat + ticketing | IL-CSB-01 | ⏳ | infra/chatwoot/ |
| 87 | TicketRoutingAgent — category + priority + SLA assignment | IL-CSB-01 | ⏳ | services/support/ |
| 88 | CustomerSupportAgent — FAQ bot + RAG (Ollama + ChromaDB) | IL-CSB-01 | ⏳ | services/support/ |
| 89 | EscalationAgent — SLA breach monitor + HITL escalation | IL-CSB-01 | ⏳ | n8n + ClickHouse |
| 90 | ComplaintTriageAgent — link to DISP workflow (IL-022) | IL-CSB-01 | ⏳ | services/support/ |
| 91 | FeedbackAnalyticsAgent — NPS/CSAT + Consumer Duty PS22/9 | IL-CSB-01 | ⏳ | ClickHouse + Superset |
| 92 | Support ClickHouse schema (tickets, SLA events, CSAT) | IL-CSB-01 | ⏳ | scripts/schema/ |
| 93 | FastAPI /v1/support endpoints (5+) | IL-CSB-01 | ⏳ | api/routers/support.py |
| 94 | Agent passports + SOUL files (5 agents) | IL-CSB-01 | ⏳ | agents/passports/support/ |
| 95 | Support Tests (60+) | IL-CSB-01 | ⏳ | tests/test_support/ |

OSS Stack: Chatwoot (MIT) + Ollama RAG + ChromaDB + n8n + ClickHouse + Superset
FCA: Consumer Duty PS22/9 §4 (Consumer Support outcome)

---

## Phase 13 — Marketing & Growth Block ⏳ PENDING

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 96 | Listmonk self-hosted (AGPL) — email campaigns | IL-MKT-01 | ⏳ | infra/listmonk/ |
| 97 | Plausible Analytics self-hosted (MIT) — privacy-first web analytics | IL-MKT-01 | ⏳ | infra/plausible/ |
| 98 | CampaignAgent — email/push campaign orchestration | IL-MKT-01 | ⏳ | services/marketing/ |
| 99 | LeadScoringAgent — behavioral scoring (ClickHouse + scikit-learn) | IL-MKT-01 | ⏳ | services/marketing/ |
| 100 | ContentAgent — compliance-safe content generation (Ollama) | IL-MKT-01 | ⏳ | services/marketing/ |
| 101 | OnboardingNurtureAgent — incomplete KYC follow-up sequences | IL-MKT-01 | ⏳ | n8n + Notifications |
| 102 | AnalyticsAgent — UTM, cohort analysis, conversion funnels | IL-MKT-01 | ⏳ | Plausible + ClickHouse |
| 103 | Marketing ClickHouse schema (campaigns, leads, events) | IL-MKT-01 | ⏳ | scripts/schema/ |
| 104 | FastAPI /v1/marketing endpoints (5+) | IL-MKT-01 | ⏳ | api/routers/marketing.py |
| 105 | FCA COBS 4 compliance gate (financial promotions review) | IL-MKT-01 | ⏳ | HITL: MLRO review |
| 106 | Agent passports + SOUL files (5 agents) | IL-MKT-01 | ⏳ | agents/passports/marketing/ |
| 107 | Marketing Tests (60+) | IL-MKT-01 | ⏳ | tests/test_marketing/ |

OSS Stack: Listmonk (AGPL) + Plausible (MIT) + Ollama + scikit-learn + n8n + ClickHouse
FCA: COBS 4 (financial promotions), Consumer Duty PS22/9 

## Sprint 16 — Customer Support + Compliance AI Merge + Agent Routing (2026-04-15)

> **Scope:** 3 blocks — (A) Customer Support Block (Phase 12), (B) Compliance AI Copilot merge from `refactor/claude-ai-scaffold` (Phase 11), (C) Agent Routing Layer foundation (Phase 8). No BT blockers.§2 (Products &
>
> ### S16-A: Customer Support Block (Phase 12) — IL-CSB-01

| # | Feature | Status | FCA ref |
|---|---------|--------|---------|
| 108 | Chatwoot docker-compose (MIT) | ⏳ | PS22/9 §4 |
| 109 | TicketRoutingAgent — SLA assignment | ⏳ | PS22/9 |
| 110 | CustomerSupportAgent — FAQ RAG bot | ⏳ | PS22/9 §4 |
| 111 | EscalationAgent — SLA breach HITL | ⏳ | DISP 1.3 |
| 112 | ComplaintTriageAgent — DISP link | ⏳ | DISP 1.6 |
| 113 | FeedbackAnalyticsAgent — NPS/CSAT | ⏳ | PS22/9 §10 |
| 114 | ClickHouse schema (tickets, CSAT) | ⏳ | — |
| 115 | FastAPI /v1/support (5+ endpoints) | ⏳ | — |
| 116 | Agent passports + SOUL (5 agents) | ⏳ | — |
| 117 | MCP Support Tools (4 tools) | ⏳ | — |
| 118 | Support Tests (60+) | ⏳ | — |Services)

### S16-B: Compliance AI Copilot — merge to main (Phase 11)

| # | Feature | IL | Status |
|---|---------|----|---------|
| 119 | Merge Compliance Knowledge Base (88 tests) | IL-CKS-01 | ⏳ |
| 120 | Merge Experiment Copilot (91 tests) | IL-CEC-01 | ⏳ |
| 121 | Merge Realtime Transaction Monitor (105 tests) | IL-RTM-01 | ⏳ |
| 122 | Resolve merge conflicts + rebase | — | ⏳ |
| 123 | Full suite green after merge (2900+) | — | ⏳ |

### S16-C: Agent Routing Layer Foundation (Phase 8)

| # | Feature | IL | Status |
|---|---------|----|---------|
| 124 | Agent Gateway + 3-Tier Worker | IL-ARL-01 | ⏳ |
| 125 | Playbook Engine (YAML rules) | IL-ARL-01 | ⏳ |
| 126 | ReasoningBank (vector + memory) | IL-ARL-01 | ⏳ |
| 127 | Swarm Orchestrator (3 topologies) | IL-ARL-01 | ⏳ |
| 128 | 5 Specialized Agents | IL-ARL-01 | ⏳ |
| 129 | Telemetry + Policy Engine | IL-ARL-01 | ⏳ |
| 130 | MCP Routing Tools (4 tools) | IL-ARL-01 | ⏳ |
| 131 | Agent Routing Tests (80+) | IL-ARL-01 | ⏳ |

### Sprint 16 Targets

| Metric | S15 | S16 Target |
|--------|-----|------------|
| Tests | 2700 | 3100+ |
| Coverage | 87% | 88%+ |
| MCP tools | 28 | 36+ |
| API endpoints | 80+ | 90+ |
| Agent passports | 9 | 14+ |

No BT blockers. BT-001..BT-007 remain BLOCKED (CEO action).
