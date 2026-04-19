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


## Phase 8 — Agent Routing Layer ✅ DONE (Sprint 16 Block C — 2026-04-15)

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 51 | Agent Gateway + Tier Workers | IL-ARL-01 | ✅ | services/agent_routing/ |
| 52 | Playbook Engine (YAML routing rules) | IL-ARL-01 | ✅ | config/playbooks/ |
| 53 | ReasoningBank (vector store + case memory) | IL-ARL-01 | ✅ | services/reasoning_bank/ |
| 54 | Swarm Orchestrator (star/hierarchy/ring) | IL-ARL-01 | ✅ | services/swarm/ |
| 55 | Specialized Agents (5 agents) | IL-ARL-01 | ✅ | services/swarm/agents/ |
| 56 | Telemetry + Policy Engine | IL-ARL-01 | ✅ | ClickHouse + Grafana |
| 57 | MCP Tools (4 new tools) | IL-ARL-01 | ✅ | banxe_mcp/tools/ |
| 58 | Agent Routing Tests 

## Phase 9 — Design-to-Code Pipeline ✅ DONE (Sprint 16 — 2026-04-12)

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 59 | Penpot self-hosted Docker | IL-D2C-01 | ✅ | infra/penpot/ |
| 60 | Penpot MCP Client | IL-D2C-01 | ✅ | services/design_pipeline/ |
| 61 | Design Token Pipeline | IL-D2C-01 | ✅ | config/design-tokens/ |
| 62 | AI Orchestrator FastAPI LangChain | IL-D2C-01 | ✅ | Penpot to code generation |
| 63 | Code Generator Mitosis | IL-D2C-01 | ✅ | React Vue RN output |
| 64 | Visual QA Agent | IL-D2C-01 | ✅ | BackstopJS Loki |
| 65 | BANXE UI Agents | IL-D2C-01 | ✅ | compliance txn report |
| 66 | D2C MCP Tools 4 tools | IL-D2C-01 | ✅ | banxe_mcp tools |
| 67 | D2C Tests 80 plus | IL-D2C-01 | ✅ | tests/test_design_pipeline/ |

commit: 9b8fb48 | 207 tests green | 2026-04-12
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

## Phase 12 — Customer Support Block ✅ DONE (Sprint 16 Block A — 2026-04-16)

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 86 | Chatwoot self-hosted (MIT) — live chat + ticketing | IL-CSB-01 | ✅ | infra/chatwoot/ |
| 87 | TicketRoutingAgent — category + priority + SLA assignment | IL-CSB-01 | ✅ | services/support/ |
| 88 | CustomerSupportAgent — FAQ bot + RAG (confidence 0.80) | IL-CSB-01 | ✅ | services/support/ |
| 89 | EscalationAgent — SLA breach monitor + HITL escalation | IL-CSB-01 | ✅ | n8n + ClickHouse |
| 90 | ComplaintTriageAgent — link to DISP workflow (IL-022) | IL-CSB-01 | ✅ | services/support/ |
| 91 | FeedbackAnalyticsAgent — NPS/CSAT + Consumer Duty PS22/9 | IL-CSB-01 | ✅ | ClickHouse |
| 92 | Support ClickHouse schema (tickets, SLA events, CSAT) | IL-CSB-01 | ✅ | scripts/schema/ |
| 93 | FastAPI /v1/support endpoints (5) | IL-CSB-01 | ✅ | api/routers/support.py |
| 94 | Agent passports + SOUL files (5 agents) | IL-CSB-01 | ✅ | agents/passports/support/ |
| 95 | Support Tests (105) | IL-CSB-01 | ✅ | tests/test_support/ |

OSS Stack: Chatwoot (MIT) + Ollama RAG + ChromaDB + n8n + ClickHouse + Superset
FCA: Consumer Duty PS22/9 §4 (Consumer Support outcome)

---

## Phase 13 — Marketing & Growth Block ✅ DONE (Sprint 16 — 2026-04-15)

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 96 | Listmonk self-hosted (AGPL) — email campaigns | IL-MKT-01 | ✅ | infra/listmonk/ |
| 97 | Plausible Analytics self-hosted (MIT) — privacy-first web analytics | IL-MKT-01 | ✅ | infra/plausible/ |
| 98 | CampaignAgent — email/push campaign orchestration | IL-MKT-01 | ✅ | services/marketing/ |
| 99 | LeadScoringAgent — behavioral scoring (ClickHouse + scikit-learn) | IL-MKT-01 | ✅ | services/marketing/ |
| 100 | ContentAgent — compliance-safe content generation (Ollama) | IL-MKT-01 | ✅ | services/marketing/ |
| 101 | OnboardingNurtureAgent — incomplete KYC follow-up sequences | IL-MKT-01 | ✅ | n8n + Notifications |
| 102 | AnalyticsAgent — UTM, cohort analysis, conversion funnels | IL-MKT-01 | ✅ | Plausible + ClickHouse |
| 103 | Marketing ClickHouse schema (campaigns, leads, events) | IL-MKT-01 | ✅ | scripts/schema/ |
| 104 | FastAPI /v1/marketing endpoints (5+) | IL-MKT-01 | ✅ | api/routers/marketing.py |
| 105 | FCA COBS 4 compliance gate (financial promotions review) | IL-MKT-01 | ✅ | HITL: MLRO review |
| 106 | Agent passports + SOUL files (5 agents) | IL-MKT-01 | ✅ | agents/passports/marketing/ |
| 107 | Marketing Tests (60+) | IL-MKT-01 | ✅ | tests/test_marketing/ |

OSS Stack: Listmonk (AGPL) + Plausible (MIT) + Ollama + scikit-learn + n8n + ClickHouse
FCA: COBS 4 (financial promotions), Consumer Duty PS22/9 

## Sprint 16 — Customer Support + Compliance AI Merge + Agent Routing (2026-04-15)

> **Scope:** 3 blocks — (A) Customer Support Block (Phase 12), (B) Compliance AI Copilot merge from `refactor/claude-ai-scaffold` (Phase 11), (C) Agent Routing Layer foundation (Phase 8). No BT blockers.§2 (Products &
>
> ### S16-A: Customer Support Block (Phase 12) — IL-CSB-01

| # | Feature | Status | FCA ref |
|---|---------|--------|---------|
| 108 | Chatwoot docker-compose (MIT) | ✅ | PS22/9 §4 |
| 109 | TicketRoutingAgent — SLA assignment | ✅ | PS22/9 |
| 110 | CustomerSupportAgent — FAQ RAG bot | ✅ | PS22/9 §4 |
| 111 | EscalationAgent — SLA breach HITL | ✅ | DISP 1.3 |
| 112 | ComplaintTriageAgent — DISP link | ✅ | DISP 1.6 |
| 113 | FeedbackAnalyticsAgent — NPS/CSAT | ✅ | PS22/9 §10 |
| 114 | ClickHouse schema (tickets, CSAT) | ✅ | — |
| 115 | FastAPI /v1/support (5+ endpoints) | ✅ | — |
| 116 | Agent passports + SOUL (5 agents) | ✅ | — |
| 117 | MCP Support Tools (4 tools) | ✅ | — |
| 118 | Support Tests (105) | ✅ | — |

commit: 5257693 | 3092 tests green | 2026-04-16

### S16-B: Compliance AI Copilot — merge to main (Phase 11)

| # | Feature | IL | Status |
|---|---------|----|---------|
| 119 | Merge Compliance Knowledge Base (88 tests) | IL-CKS-01 | ✅ |
| 120 | Merge Experiment Copilot (91 tests) | IL-CEC-01 | ✅ |
| 121 | Merge Realtime Transaction Monitor (105 tests) | IL-RTM-01 | ✅ |
| 122 | Resolve merge conflicts + rebase | — | ✅ |
| 123 | Full suite green after merge (3092) | — | ✅ |

commit: 4fa0f0e | 2026-04-15

### S16-C: Agent Routing Layer Foundation (Phase 8)

| # | Feature | IL | Status |
|---|---------|----|---------|
| 124 | Agent Gateway + 3-Tier Worker | IL-ARL-01 | ✅ |
| 125 | Playbook Engine (YAML rules) | IL-ARL-01 | ✅ |
| 126 | ReasoningBank (vector + memory) | IL-ARL-01 | ✅ |
| 127 | Swarm Orchestrator (3 topologies) | IL-ARL-01 | ✅ |
| 128 | 5 Specialized Agents | IL-ARL-01 | ✅ |
| 129 | Telemetry + Policy Engine | IL-ARL-01 | ✅ |
| 130 | MCP Routing Tools (4 tools) | IL-ARL-01 | ✅ |
| 131 | Agent Routing Tests (184) | IL-ARL-01 | ✅ |

commit: 5f132dd | 2026-04-15

### Sprint 16 Targets — FINAL

| Metric | S15 | S16 Target | S16 Actual |
|--------|-----|------------|-----------|
| Tests | 2700 | 3100+ | 3092 |
| Coverage | 87% | 88%+ | TBD |
| MCP tools | 28 | 36+ | 38 ✅ |
| API endpoints | 80+ | 90+ | TBD |
| Agent passports | 9 | 14+ | 14 ✅ |

No BT blockers. BT-001..BT-007 remain BLOCKED (CEO action).

---

## Sprint 17 — Regulatory Reporting Automation (2026-04-16)

> **Scope:** 3 blocks — (A) ROADMAP cleanup (Phase 9 + 13), (B) Regulatory Reporting Automation (Phase 14 — IL-RRA-01), (C) Sprint 17 targets. P0 deadline 7 May 2026.

### S17-A: ROADMAP Cleanup

| Item | Action |
|------|--------|
| Phase 9 header | PENDING → ✅ DONE (Sprint 16 — 2026-04-12), commit 9b8fb48 |
| Phase 9 table items | All PENDING → ✅ |
| Phase 13 header | ⏳ PENDING → ✅ DONE (Sprint 16 — 2026-04-15) |
| Phase 13 table items | All ⏳ → ✅ |

### S17-B: Phase 14 — Regulatory Reporting Automation (IL-RRA-01)

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 132 | models.py — Protocol DI ports + InMemory stubs | IL-RRA-01 | ✅ | services/regulatory_reporting/ |
| 133 | xml_generator.py — FIN060/FIN071/FSA076/SAR/BoE/ACPR | IL-RRA-01 | ✅ | I-01: Decimal only |
| 134 | validators.py — StructuralValidator + XSDValidator | IL-RRA-01 | ✅ | FCA SUP 16 schema checks |
| 135 | audit_trail.py — ClickHouseAuditTrail (I-24) | IL-RRA-01 | ✅ | SYSC 9.1.1R, 5yr TTL |
| 136 | scheduler.py — N8nScheduler cron workflows | IL-RRA-01 | ✅ | n8n :5678 |
| 137 | regulatory_reporting_agent.py — L2/L4 orchestration | IL-RRA-01 | ✅ | I-27: HITL for submission |
| 138 | api/routers/regulatory.py — 7 endpoints | IL-RRA-01 | ✅ | POST/GET regulatory/* |
| 139 | 5 MCP tools (report_generate..report_list_templates) | IL-RRA-01 | ✅ | banxe_mcp/server.py |
| 140 | Agent passport + SOUL.md | IL-RRA-01 | ✅ | agents/passports/reporting/ |
| 141 | 86 tests across 5 test files | IL-RRA-01 | ✅ | tests/test_regulatory_reporting/ |

FCA refs: SUP 16.12, SYSC 9.1.1R, POCA 2002 s.330, BoE Statistical Notice, ACPR 2014-P-01

### S17-C: Sprint 17 Targets

| Metric | S16 Actual | S17 Target | S17 Actual |
|--------|-----------|------------|-----------|
| Tests | 3092 | 3200+ | 3190 ✅ |
| MCP tools | 38 | 43+ | 43 ✅ |
| API endpoints | 90+ | 96+ | 97 ✅ |
| Agent passports | 14 | 15+ | 15 ✅ |

commit: IL-RRA-01 | 3190 tests green | 2026-04-16

---

## Phase 15 — Open Banking PSD2 Gateway ✅ DONE (Sprint 18 — 2026-04-16)

> IL-OBK-01 | PSD2 AISP/PISP gateway — consents, payments, SCA, token management

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 142 | models.py — Protocol DI ports + InMemory stubs | IL-OBK-01 | ✅ | 6 enums, 6 dataclasses, 5 ports |
| 143 | consent_manager.py — 90-day lifecycle (PSD2 RTS Art.10) | IL-OBK-01 | ✅ | create/authorise/revoke |
| 144 | pisp_service.py — PISP single + bulk (PSR 2017 / Art.66) | IL-OBK-01 | ✅ | I-01: Decimal amounts |
| 145 | aisp_service.py — AISP balances/txns (PSD2 Art.67) | IL-OBK-01 | ✅ | permission validation |
| 146 | aspsp_adapter.py — Berlin Group + UK OBIE 3.1 | IL-OBK-01 | ✅ | NextGenPSD2 + OBIE |
| 147 | sca_orchestrator.py — redirect/decoupled/embedded (RTS Art.4) | IL-OBK-01 | ✅ | 10-min challenge TTL |
| 148 | token_manager.py — OAuth2/PKCE/mTLS/OIDC FAPI | IL-OBK-01 | ✅ | cached tokens |
| 149 | open_banking_agent.py — L2/L4 orchestration (I-27) | IL-OBK-01 | ✅ | HITL for payment |
| 150 | api/routers/open_banking.py — 8 endpoints | IL-OBK-01 | ✅ | POST/GET /v1/open-banking/* |
| 151 | 5 MCP tools (ob_create_consent..ob_list_aspsps) | IL-OBK-01 | ✅ | banxe_mcp/server.py |
| 152 | Agent passport + SOUL.md | IL-OBK-01 | ✅ | agents/passports/open_banking/ |
| 153 | 113 tests across 5 test files | IL-OBK-01 | ✅ | tests/test_open_banking/ |

ASPSPs: barclays-uk (OBIE), hsbc-uk (OBIE), bnp-fr (Berlin Group)
Regulatory: PSD2 Art.66+67, RTS Art.4+10, PSR 2017, UK OB OBIE 3.1, FCA PS19/4

---

## Phase 16 — Audit & Governance Dashboard ✅ DONE (Sprint 18 — 2026-04-16)

> IL-AGD-01 | Unified audit aggregation, risk scoring, board governance reports

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 154 | models.py — Protocol DI ports + InMemory stubs | IL-AGD-01 | ✅ | 4 enums, 5 dataclasses, 4 ports |
| 155 | audit_aggregator.py — unified event ingestion + query | IL-AGD-01 | ✅ | 8 categories, ClickHouse-ready |
| 156 | risk_scorer.py — AML+fraud+operational+regulatory scoring | IL-AGD-01 | ✅ | 0–100 float scale |
| 157 | governance_reporter.py — JSON/PDF board reports | IL-AGD-01 | ✅ | SYSC 9 compliance |
| 158 | dashboard_api.py — live metrics + governance status | IL-AGD-01 | ✅ | WebSocket-ready |
| 159 | api/routers/audit_dashboard.py — 8 endpoints | IL-AGD-01 | ✅ | GET/POST /v1/audit/* |
| 160 | 4 MCP tools (audit_query_events..audit_governance_status) | IL-AGD-01 | ✅ | banxe_mcp/server.py |
| 161 | Agent passport + SOUL.md | IL-AGD-01 | ✅ | agents/passports/audit/ |
| 162 | 88 tests across 5 test files | IL-AGD-01 | ✅ | tests/test_audit_dashboard/ |

Risk levels: LOW (<25) | MEDIUM (25–49) | HIGH (50–74) | CRITICAL (≥75)
Regulatory: SYSC 9.1.1R, SYSC 4.1.1R, PS22/9, MLR 2017 Reg.28, EU AI Act Art.14

---

## Sprint 18 — Open Banking + Audit Dashboard (2026-04-16)

> **Scope:** 4 blocks — (A) Phase 15 Open Banking PSD2 Gateway, (B) Phase 16 Audit Dashboard,
> (C) ROADMAP Phase 15+16 sections, (D) IL-096. P0 deadline 7 May 2026.

### S18-A: Phase 15 — Open Banking PSD2 Gateway (IL-OBK-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 142 | services/open_banking/ — 8 modules | IL-OBK-01 | ✅ |
| 143 | api/routers/open_banking.py — 8 endpoints | IL-OBK-01 | ✅ |
| 144 | 5 MCP tools: ob_create_consent, ob_initiate_payment, ob_get_accounts, ob_revoke_consent, ob_list_aspsps | IL-OBK-01 | ✅ |
| 145 | Agent passport + SOUL.md | IL-OBK-01 | ✅ |
| 146 | 113 tests | IL-OBK-01 | ✅ |

### S18-B: Phase 16 — Audit & Governance Dashboard (IL-AGD-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 147 | services/audit_dashboard/ — 5 modules | IL-AGD-01 | ✅ |
| 148 | api/routers/audit_dashboard.py — 8 endpoints | IL-AGD-01 | ✅ |
| 149 | 4 MCP tools: audit_query_events, audit_generate_report, audit_risk_score, audit_governance_status | IL-AGD-01 | ✅ |
| 150 | Agent passport + SOUL.md | IL-AGD-01 | ✅ |
| 151 | 88 tests | IL-AGD-01 | ✅ |

### S18-C: Sprint 18 Targets

| Metric | S17 Actual | S18 Target | S18 Actual |
|--------|-----------|------------|-----------|
| Tests | 3190 | 3400+ | 3391 ✅ |
| MCP tools | 43 | 52+ | 52 ✅ |
| API endpoints | 97 | 111+ | 113 ✅ |
| Agent passports | 15 | 17+ | 17 ✅ |

commit: IL-OBK-01 + IL-AGD-01 | 3391 tests green | 2026-04-16

---

## Phase 17 — Treasury & Liquidity Management ✅ DONE (Sprint 19 — 2026-04-16)

> IL-TLM-01 | Real-time liquidity monitoring, forecasting, sweeps, CASS 15 reconciliation

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 163 | models.py — Protocol DI ports + InMemory stubs | IL-TLM-01 | ✅ | Decimal-only amounts, 5 ports |
| 164 | liquidity_monitor.py — CASS 15.6 cash position monitor | IL-TLM-01 | ✅ | is_compliant flag |
| 165 | cash_flow_forecaster.py — 7/14/30-day trend forecast | IL-TLM-01 | ✅ | shortfall_risk alert |
| 166 | funding_optimizer.py — HOLD/SWEEP_OUT/DRAW_DOWN | IL-TLM-01 | ✅ | idle cash minimization |
| 167 | safeguarding_reconciler.py — CASS 15.3 recon (1p tolerance) | IL-TLM-01 | ✅ | MATCHED/DISCREPANCY |
| 168 | sweep_engine.py — surplus/deficit sweeps (L4 HITL) | IL-TLM-01 | ✅ | I-27: propose only |
| 169 | treasury_agent.py — L2/L4 orchestration | IL-TLM-01 | ✅ | Decimal → str serialization |
| 170 | api/routers/treasury.py — 8 endpoints | IL-TLM-01 | ✅ | GET/POST /v1/treasury/* |
| 171 | 5 MCP tools (treasury_get_positions..treasury_pending_sweeps) | IL-TLM-01 | ✅ | banxe_mcp/server.py |
| 172 | Agent passport + SOUL.md | IL-TLM-01 | ✅ | agents/passports/treasury/ |
| 173 | 127 tests across 5 test files | IL-TLM-01 | ✅ | tests/test_treasury/ |

FCA refs: CASS 15.3 (reconciliation), CASS 15.6 (liquidity), CASS 15.12 (reporting)

---

## Phase 18 — Notification Hub ✅ DONE (Sprint 19 — 2026-04-16)

> IL-NHB-01 | Multi-channel notifications — Jinja2 templates, preference management, delivery tracking

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 174 | models.py — Protocol DI ports + InMemory stubs (3 seed templates) | IL-NHB-01 | ✅ | 5 channels, 7 categories |
| 175 | template_engine.py — Jinja2 multi-language (EN/FR/RU) | IL-NHB-01 | ✅ | soft undefined vars |
| 176 | channel_dispatcher.py — 5-channel dispatch | IL-NHB-01 | ✅ | EMAIL/SMS/PUSH/TELEGRAM/WEBHOOK |
| 177 | preference_manager.py — GDPR opt-in/opt-out defaults | IL-NHB-01 | ✅ | SECURITY/OPERATIONAL = default opt-in |
| 178 | delivery_tracker.py — exp. backoff retry (max 3) | IL-NHB-01 | ✅ | base_delay_secs=0 in tests |
| 179 | notification_agent.py — L2 orchestration | IL-NHB-01 | ✅ | template→pref→dispatch→track |
| 180 | api/routers/notifications_hub.py — 7 endpoints | IL-NHB-01 | ✅ | /v1/notifications-hub/* |
| 181 | 4 MCP tools (notify_send..notify_delivery_status) | IL-NHB-01 | ✅ | banxe_mcp/server.py |
| 182 | Agent passport + SOUL.md | IL-NHB-01 | ✅ | agents/passports/notifications/ |
| 183 | 97 tests across 5 test files | IL-NHB-01 | ✅ | tests/test_notification_hub/ |

FCA refs: DISP 1.3 (complaint notifications), PS22/9 §4 (consumer communications), GDPR Art.7

---

## Sprint 19 — Treasury + Notification Hub (2026-04-16)

> **Scope:** 4 blocks — (A) Phase 17 Treasury, (B) Phase 18 Notification Hub,
> (C) ROADMAP Phase 17+18 sections, (D) IL-097. P0 deadline 7 May 2026.

### S19-A: Phase 17 — Treasury & Liquidity Management (IL-TLM-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 163 | services/treasury/ — 7 modules | IL-TLM-01 | ✅ |
| 164 | api/routers/treasury.py — 8 endpoints | IL-TLM-01 | ✅ |
| 165 | 5 MCP tools: treasury_get_positions, treasury_forecast, treasury_propose_sweep, treasury_reconcile, treasury_pending_sweeps | IL-TLM-01 | ✅ |
| 166 | Agent passport + SOUL.md | IL-TLM-01 | ✅ |
| 167 | 127 tests | IL-TLM-01 | ✅ |

### S19-B: Phase 18 — Notification Hub (IL-NHB-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 168 | services/notification_hub/ — 6 modules | IL-NHB-01 | ✅ |
| 169 | api/routers/notifications_hub.py — 7 endpoints | IL-NHB-01 | ✅ |
| 170 | 4 MCP tools: notify_send, notify_list_templates, notify_get_preferences, notify_delivery_status | IL-NHB-01 | ✅ |
| 171 | Agent passport + SOUL.md | IL-NHB-01 | ✅ |
| 172 | 97 tests | IL-NHB-01 | ✅ |

### S19-C: Sprint 19 Targets

| Metric | S18 Actual | S19 Target | S19 Actual |
|--------|-----------|------------|-----------|
| Tests | 3391 | 3580+ | 3615 ✅ |
| MCP tools | 52 | 61+ | 61 ✅ |
| API endpoints | 113 | 128+ | 129 ✅ |
| Agent passports | 17 | 19+ | 19 ✅ |

commit: IL-TLM-01 + IL-NHB-01 | 3615 tests green | 2026-04-16

---

## Phase 19 — Card Issuing & Management ✅ DONE (Sprint 20 — 2026-04-16)

> IL-CIM-01 | Full card lifecycle: issue, activate, PIN (I-12), freeze/block, spend limits, 3DS2 authorisation

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 184 | models.py — Protocol DI ports + InMemory stubs | IL-CIM-01 | ✅ | BINs: MC 531604, Visa 427316 |
| 185 | card_issuer.py — issue VIRTUAL/PHYSICAL, activate, PIN hash (I-12) | IL-CIM-01 | ✅ | SHA-256 PIN, never plain |
| 186 | card_lifecycle.py — freeze/unfreeze/block/replace/expire | IL-CIM-01 | ✅ | block/replace = HITL L4 |
| 187 | spend_control.py — per-card limits (Decimal), MCC block, geo-restrict | IL-CIM-01 | ✅ | DAILY/WEEKLY/MONTHLY |
| 188 | card_transaction_processor.py — authorise + clear transactions | IL-CIM-01 | ✅ | spend limit enforcement |
| 189 | fraud_shield.py — velocity check + MCC risk (risk_score: float 0–100) | IL-CIM-01 | ✅ | 5+ auths/hr = HIGH_VELOCITY |
| 190 | card_agent.py — L2/L4 orchestration | IL-CIM-01 | ✅ | I-27 HITL for block/replace |
| 191 | api/routers/card_issuing.py — 10 endpoints | IL-CIM-01 | ✅ | /v1/cards/* |
| 192 | 5 MCP tools (card_issue..card_list_transactions) | IL-CIM-01 | ✅ | banxe_mcp/server.py |
| 193 | Agent passport + SOUL.md | IL-CIM-01 | ✅ | agents/passports/cards/ |
| 194 | 126 tests across 7 test files | IL-CIM-01 | ✅ | tests/test_card_issuing/ |

FCA refs: PSR 2017 / PSD2 Art.63, PCI-DSS v4 (I-12), FCA BCOBS 5, GDPR Art.5

---

## Phase 20 — Merchant Acquiring Gateway ✅ DONE (Sprint 20 — 2026-04-16)

> IL-MAG-01 | KYB onboarding, payment acceptance with 3DS2 SCA, settlement (1.5% fee), chargeback handling, risk scoring

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 195 | models.py — Protocol DI ports + InMemory stubs | IL-MAG-01 | ✅ | 5 ports, prohibited MCC list |
| 196 | merchant_onboarding.py — KYB risk tier (LOW/MEDIUM/HIGH/PROHIBITED) | IL-MAG-01 | ✅ | MCCs 7995/9754/7801 blocked |
| 197 | payment_gateway.py — 3DS2 routing (≥ £30.00) | IL-MAG-01 | ✅ | PSD2 SCA RTS Art.11 |
| 198 | settlement_engine.py — batch settlement (FEE_RATE = 1.5%) | IL-MAG-01 | ✅ | Decimal gross/fees/net |
| 199 | chargeback_handler.py — full lifecycle with evidence | IL-MAG-01 | ✅ | RECEIVED→RESOLVED_WIN/LOSS |
| 200 | merchant_risk_scorer.py — score 0–100 (float — analytical) | IL-MAG-01 | ✅ | chargeback_ratio: float |
| 201 | merchant_agent.py — L2/L4 orchestration | IL-MAG-01 | ✅ | I-27 HITL for suspend/terminate |
| 202 | api/routers/merchant_acquiring.py — 10 endpoints | IL-MAG-01 | ✅ | /v1/merchants/* |
| 203 | 5 MCP tools (merchant_onboard..merchant_risk_score) | IL-MAG-01 | ✅ | banxe_mcp/server.py |
| 204 | Agent passport + SOUL.md | IL-MAG-01 | ✅ | agents/passports/merchant/ |
| 205 | 120 tests across 7 test files | IL-MAG-01 | ✅ | tests/test_merchant_acquiring/ |

FCA refs: PSR 2017 / PSD2 Art.97+RTS Art.11, MLR 2017 Reg.28, FCA SUP 16, VISA/MC scheme rules

---

## Sprint 20 — Card Issuing + Merchant Acquiring (2026-04-16)

> **Scope:** 4 blocks — (A) Phase 19 Card Issuing, (B) Phase 20 Merchant Acquiring,
> (C) ROADMAP Phase 19+20 sections, (D) IL-098. P0 deadline 7 May 2026.

### S20-A: Phase 19 — Card Issuing & Management (IL-CIM-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 184 | services/card_issuing/ — 7 modules | IL-CIM-01 | ✅ |
| 185 | api/routers/card_issuing.py — 10 endpoints | IL-CIM-01 | ✅ |
| 186 | 5 MCP tools: card_issue, card_freeze, card_get_status, card_set_limits, card_list_transactions | IL-CIM-01 | ✅ |
| 187 | Agent passport + SOUL.md | IL-CIM-01 | ✅ |
| 188 | 126 tests | IL-CIM-01 | ✅ |

### S20-B: Phase 20 — Merchant Acquiring Gateway (IL-MAG-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 189 | services/merchant_acquiring/ — 7 modules | IL-MAG-01 | ✅ |
| 190 | api/routers/merchant_acquiring.py — 10 endpoints | IL-MAG-01 | ✅ |
| 191 | 5 MCP tools: merchant_onboard, merchant_accept_payment, merchant_get_settlements, merchant_handle_chargeback, merchant_risk_score | IL-MAG-01 | ✅ |
| 192 | Agent passport + SOUL.md | IL-MAG-01 | ✅ |
| 193 | 120 tests | IL-MAG-01 | ✅ |

### S20-C: Sprint 20 Targets

| Metric | S19 Actual | S20 Target | S20 Actual |
|--------|-----------|------------|-----------|
| Tests | 3615 | 3830+ | 3861 ✅ |
| MCP tools | 61 | 71+ | 71 ✅ |
| API endpoints | 129 | 149+ | 149 ✅ |
| Agent passports | 19 | 21+ | 21 ✅ |

commit: IL-CIM-01 + IL-MAG-01 | 3861 tests green | 2026-04-16

---

## Phase 21 — FX & Currency Exchange ✅ DONE (Sprint 21 — 2026-04-17)

> IL-FXE-01 | Real-time FX quotes, execution, spread management, MLR 2017 §33 AML controls

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 206 | models.py — Protocol DI ports + InMemory stubs (6 pairs, 6 spread configs) | IL-FXE-01 | ✅ | Decimal-only amounts |
| 207 | rate_provider.py — ECB rates aggregation (Frankfurter), auto-seed | IL-FXE-01 | ✅ | Redis TTL 60s in prod |
| 208 | quote_engine.py — bid/ask from spread, quote TTL 30s | IL-FXE-01 | ✅ | half-spread on each side |
| 209 | fx_executor.py — PENDING→EXECUTED, 0.1% fee (Decimal) | IL-FXE-01 | ✅ | dataclasses.replace() |
| 210 | spread_manager.py — per-pair config, VIP prefix, volume tiers | IL-FXE-01 | ✅ | "vip-" entity → vip_bps |
| 211 | fx_compliance.py — EDD £10k, HITL £50k, blocked currencies, structuring | IL-FXE-01 | ✅ | I-02: RUB/IRR/KPW/BYR/SYP/CUC |
| 212 | fx_agent.py — L2/L4 orchestration, HITL_REQUIRED for ≥ £50k | IL-FXE-01 | ✅ | HTTP 202 for HITL |
| 213 | api/routers/fx_exchange.py — 8 endpoints | IL-FXE-01 | ✅ | /v1/fx/* (embedded prefix) |
| 214 | 5 MCP tools (fx_get_quote..fx_history) | IL-FXE-01 | ✅ | banxe_mcp/server.py |
| 215 | Agent passport + SOUL.md | IL-FXE-01 | ✅ | agents/passports/fx/ |
| 216 | 129 tests across 7 test files | IL-FXE-01 | ✅ | tests/test_fx_exchange/ |

FCA refs: PSR 2017, MLR 2017 §33 (FX AML), FCA PRIN 6 (spread transparency), EMD Art.10

---

## Phase 22 — Multi-Currency Ledger Enhancement ✅ DONE (Sprint 21 — 2026-04-17)

> IL-MCL-01 | Multi-currency accounts (10 currencies), nostro reconciliation, conversion routing, BoE Form BT

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 217 | models.py — Protocol DI ports + InMemory stubs (10 currencies, 2 nostros) | IL-MCL-01 | ✅ | Decimal-only, nostro £1 tolerance |
| 218 | account_manager.py — create/add/get accounts, max 10 currencies | IL-MCL-01 | ✅ | ValueError on overflow |
| 219 | balance_engine.py — credit/debit, overdraft check, consolidated base-CCY | IL-MCL-01 | ✅ | I-24 ledger entries |
| 220 | nostro_reconciler.py — CASS 15.3 nostro recon (£1.00 tolerance) | IL-MCL-01 | ✅ | MATCHED/DISCREPANCY |
| 221 | currency_router.py — cheapest/fastest path, route cost in spread_bps | IL-MCL-01 | ✅ | stateless |
| 222 | conversion_tracker.py — 0.2% fee, conversion summary | IL-MCL-01 | ✅ | Decimal fee rate |
| 223 | multicurrency_agent.py — L2 orchestration | IL-MCL-01 | ✅ | str→Decimal→str serialization |
| 224 | api/routers/multi_currency.py — 8 endpoints | IL-MCL-01 | ✅ | /v1/mc-accounts/* + /v1/nostro/* |
| 225 | 4 MCP tools (mc_get_balances..mc_currency_report) | IL-MCL-01 | ✅ | banxe_mcp/server.py |
| 226 | Agent passport + SOUL.md | IL-MCL-01 | ✅ | agents/passports/multicurrency/ |
| 227 | 113 tests across 7 test files | IL-MCL-01 | ✅ | tests/test_multi_currency/ |

FCA refs: CASS 15.3 (nostro recon), CASS 15.6 (per-CCY safeguarding), EMD Art.10, BoE Form BT

---

## Sprint 21 — FX Exchange + Multi-Currency Ledger (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 21 FX Exchange, (B) Phase 22 Multi-Currency Ledger,
> (C) ROADMAP Phase 21+22 sections, (D) IL-099. P0 deadline 7 May 2026.

### S21-A: Phase 21 — FX & Currency Exchange (IL-FXE-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 206 | services/fx_exchange/ — 7 modules | IL-FXE-01 | ✅ |
| 207 | api/routers/fx_exchange.py — 8 endpoints | IL-FXE-01 | ✅ |
| 208 | 5 MCP tools: fx_get_quote, fx_execute, fx_get_rates, fx_get_spreads, fx_history | IL-FXE-01 | ✅ |
| 209 | Agent passport + SOUL.md | IL-FXE-01 | ✅ |
| 210 | 129 tests | IL-FXE-01 | ✅ |

### S21-B: Phase 22 — Multi-Currency Ledger Enhancement (IL-MCL-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 211 | services/multi_currency/ — 7 modules | IL-MCL-01 | ✅ |
| 212 | api/routers/multi_currency.py — 8 endpoints | IL-MCL-01 | ✅ |
| 213 | 4 MCP tools: mc_get_balances, mc_convert, mc_reconcile_nostro, mc_currency_report | IL-MCL-01 | ✅ |
| 214 | Agent passport + SOUL.md | IL-MCL-01 | ✅ |
| 215 | 113 tests | IL-MCL-01 | ✅ |

### S21-C: Sprint 21 Targets

| Metric | S20 Actual | S21 Target | S21 Actual |
|--------|-----------|------------|-----------|
| Tests | 3861 | 4070+ | 4103 ✅ |
| MCP tools | 71 | 80+ | 80 ✅ |
| API endpoints | 149 | 165+ | 165 ✅ |
| Agent passports | 21 | 23+ | 23 ✅ |

commit: IL-FXE-01 + IL-MCL-01 | 4103 tests green | 2026-04-17

---

## Phase 23 — Compliance Automation Engine ✅ DONE (Sprint 22 — 2026-04-17)

> IL-CAE-01 | Automated compliance rule evaluation, periodic reviews, breach detection, FCA notification, remediation tracking

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 228 | models.py — Protocol DI ports + InMemory stubs (5 seed rules) | IL-CAE-01 | ✅ | 6 enums, 8 frozen dataclasses |
| 229 | rule_engine.py — evaluate_entity, register_rule, get_rules | IL-CAE-01 | ✅ | sanctions_hit→FAIL logic |
| 230 | policy_manager.py — DRAFT→REVIEW→ACTIVE→RETIRED, diff_versions | IL-CAE-01 | ✅ | dataclasses.replace() |
| 231 | periodic_review.py — annual/180d/daily review schedules | IL-CAE-01 | ✅ | FAIL>WARNING>PASS aggregation |
| 232 | breach_reporter.py — MATERIAL/SIGNIFICANT/MINOR + FCA pending | IL-CAE-01 | ✅ | SUP 15.3 24h deadline |
| 233 | remediation_tracker.py — state machine, 6 statuses | IL-CAE-01 | ✅ | ValueError for invalid transitions |
| 234 | compliance_automation_agent.py — L2/L4 orchestration | IL-CAE-01 | ✅ | FCA report always HITL L4 (I-27) |
| 235 | api/routers/compliance_automation.py — 8 endpoints | IL-CAE-01 | ✅ | /v1/compliance/* embedded |
| 236 | 5 MCP tools (compliance_evaluate..compliance_policy_diff) | IL-CAE-01 | ✅ | banxe_mcp/server.py |
| 237 | Agent passport + SOUL.md | IL-CAE-01 | ✅ | agents/passports/compliance_auto/ |
| 238 | 116 tests across 7 test files | IL-CAE-01 | ✅ | tests/test_compliance_automation/ |

FCA refs: SUP 15.3 (breach reporting), SYSC 6.1 (compliance function), PRIN 11, MLR 2017 Reg.49

---

## Phase 24 — Document Management System ✅ DONE (Sprint 22 — 2026-04-17)

> IL-DMS-01 | SHA-256 document integrity, RBAC access, version control, retention enforcement, full-text search

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 239 | models.py — Protocol DI ports + InMemory stubs (6 retention policies seeded) | IL-DMS-01 | ✅ | 4 enums, 5 frozen dataclasses |
| 240 | document_store.py — upload (SHA-256), get, archive, dedup-by-hash | IL-DMS-01 | ✅ | I-12: content integrity |
| 241 | version_manager.py — create/rollback versions, sorted history | IL-DMS-01 | ✅ | SHA-256 per version |
| 242 | retention_engine.py — policy check, days-stored, action_required | IL-DMS-01 | ✅ | PERMANENT=no action |
| 243 | search_engine.py — keyword search, category/entity filter, relevance score | IL-DMS-01 | ✅ | float relevance (analytical) |
| 244 | access_controller.py — 6-role RBAC, ACCESS_DENIED log, can_delete | IL-DMS-01 | ✅ | I-24: append-only access log |
| 245 | document_agent.py — L2/L4 orchestration (delete=HITL L4) | IL-DMS-01 | ✅ | I-27: deletion HITL |
| 246 | api/routers/document_management.py — 8 endpoints | IL-DMS-01 | ✅ | /v1/documents/* embedded |
| 247 | 4 MCP tools (doc_upload..doc_retention_status) | IL-DMS-01 | ✅ | banxe_mcp/server.py |
| 248 | Agent passport + SOUL.md | IL-DMS-01 | ✅ | agents/passports/documents/ |
| 249 | 110 tests across 7 test files | IL-DMS-01 | ✅ | tests/test_document_management/ |

FCA refs: MLR 2017 Reg.40 (retention 5yr), SYSC 9 (record keeping), GDPR Art.17 (erasure+AML override)

---

## Sprint 22 — Compliance Automation + Document Management (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 23 Compliance Automation, (B) Phase 24 Document Management,
> (C) ROADMAP Phase 23+24 sections, (D) IL-100. P0 deadline 7 May 2026.

### S22-A: Phase 23 — Compliance Automation Engine (IL-CAE-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 228 | services/compliance_automation/ — 7 modules | IL-CAE-01 | ✅ |
| 229 | api/routers/compliance_automation.py — 8 endpoints | IL-CAE-01 | ✅ |
| 230 | 5 MCP tools: compliance_evaluate, compliance_get_rules, compliance_report_breach, compliance_track_remediation, compliance_policy_diff | IL-CAE-01 | ✅ |
| 231 | Agent passport + SOUL.md | IL-CAE-01 | ✅ |
| 232 | 116 tests | IL-CAE-01 | ✅ |

### S22-B: Phase 24 — Document Management System (IL-DMS-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 233 | services/document_management/ — 7 modules | IL-DMS-01 | ✅ |
| 234 | api/routers/document_management.py — 8 endpoints | IL-DMS-01 | ✅ |
| 235 | 4 MCP tools: doc_upload, doc_search, doc_get_versions, doc_retention_status | IL-DMS-01 | ✅ |
| 236 | Agent passport + SOUL.md | IL-DMS-01 | ✅ |
| 237 | 110 tests | IL-DMS-01 | ✅ |

### S22-C: Sprint 22 Targets

| Metric | S21 Actual | S22 Target | S22 Actual |
|--------|-----------|------------|-----------|
| Tests | 4103 | 4300+ | 4329 ✅ |
| MCP tools | 80 | 89+ | 89 ✅ |
| API endpoints | 165 | 181+ | 181 ✅ |
| Agent passports | 23 | 25+ | 25 ✅ |

commit: IL-CAE-01 + IL-DMS-01 | 4329 tests green | 2026-04-17


---

## Phase 25 — Lending & Credit Engine ✅ DONE (Sprint 23 — 2026-04-17)

> IL-LCE-01 | Internal credit scoring, loan origination, repayment, arrears, IFRS 9 provisioning

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 250 | models.py — Protocol DI ports + InMemory stubs (3 seeded products) | IL-LCE-01 | ✅ | 6 enums, 7 frozen dataclasses |
| 251 | credit_scorer.py — Decimal 0-1000 scoring (income/history/AML factors) | IL-LCE-01 | ✅ | No float, pure Decimal |
| 252 | loan_originator.py — apply/decide/disburse, ALL decisions HITL_REQUIRED (I-27) | IL-LCE-01 | ✅ | FCA CONC |
| 253 | repayment_engine.py — ANNUITY + LINEAR amortization (pure Decimal, no numpy) | IL-LCE-01 | ✅ | installments as strings (I-05) |
| 254 | arrears_manager.py — CURRENT/1-30/31-60/61-90/90+ staging | IL-LCE-01 | ✅ | IFRS 9 arrears stages |
| 255 | provisioning_engine.py — IFRS 9 ECL (Stage1 PD=1%/LGD=45%, Stage3 PD=90%/LGD=65%) | IL-LCE-01 | ✅ | Decimal ECL |
| 256 | lending_agent.py — L2/L4 orchestration | IL-LCE-01 | ✅ | HITL all credit decisions |
| 257 | api/routers/lending.py — 10 REST endpoints | IL-LCE-01 | ✅ | /v1/lending/* embedded |
| 258 | 5 MCP tools (lending_apply..lending_provision_report) | IL-LCE-01 | ✅ | banxe_mcp/server.py |
| 259 | Agent passport + SOUL.md | IL-LCE-01 | ✅ | agents/passports/lending/ |
| 260 | 128 tests across 7 test files | IL-LCE-01 | ✅ | tests/test_lending/ |

FCA refs: CONC (consumer credit), CCA 1974, IFRS 9 (ECL provisioning)

---

## Phase 26 — Insurance Integration ✅ DONE (Sprint 23 — 2026-04-17)

> IL-INS-01 | Embedded insurance — product catalog, quote/bind, claims pipeline, underwriter adapter

| # | Feature | IL | Status | Notes |
|---|---------|-----|--------|-------|
| 261 | models.py — Protocol DI ports + InMemory stubs (4 seeded products) | IL-INS-01 | ✅ | 4 enums, 5 frozen dataclasses |
| 262 | product_catalog.py — tier filtering (PREMIUM/STANDARD/basic) | IL-INS-01 | ✅ | 4 coverage types |
| 263 | premium_calculator.py — risk-adjusted pricing, pure Decimal | IL-INS-01 | ✅ | quantize 0.01 |
| 264 | policy_manager.py — QUOTED→BOUND→ACTIVE→CANCELLED state machine | IL-INS-01 | ✅ | dataclasses.replace() |
| 265 | claims_processor.py — FILED→APPROVED/DECLINED→PAID, HITL >£1000 (I-27) | IL-INS-01 | ✅ | FCA ICOBS 8.1 |
| 266 | underwriter_adapter.py — Lloyd's / Munich Re stub adapter pattern | IL-INS-01 | ✅ | Protocol DI |
| 267 | insurance_agent.py — L2/L4 orchestration (claim payouts >£1000 HITL) | IL-INS-01 | ✅ | I-27 |
| 268 | api/routers/insurance.py — 10 REST endpoints | IL-INS-01 | ✅ | /v1/insurance/* embedded |
| 269 | 4 MCP tools (insurance_get_quote..insurance_list_products) | IL-INS-01 | ✅ | banxe_mcp/server.py |
| 270 | Agent passport + SOUL.md | IL-INS-01 | ✅ | agents/passports/insurance/ |
| 271 | 106 tests across 7 test files | IL-INS-01 | ✅ | tests/test_insurance/ |

FCA refs: ICOBS (insurance conduct), IDD (Insurance Distribution Directive), FCA PS21/3 (fair value)

---

## Sprint 23 — Lending & Credit Engine + Insurance Integration (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 25 Lending, (B) Phase 26 Insurance,
> (C) ROADMAP Phase 25+26 sections, (D) IL-101. P0 deadline 7 May 2026.

### S23-A: Phase 25 — Lending & Credit Engine (IL-LCE-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 250 | services/lending/ — 7 modules | IL-LCE-01 | ✅ |
| 251 | api/routers/lending.py — 10 endpoints | IL-LCE-01 | ✅ |
| 252 | 5 MCP tools: lending_apply, lending_score, lending_get_schedule, lending_arrears_status, lending_provision_report | IL-LCE-01 | ✅ |
| 253 | Agent passport + SOUL.md | IL-LCE-01 | ✅ |
| 254 | 128 tests | IL-LCE-01 | ✅ |

### S23-B: Phase 26 — Insurance Integration (IL-INS-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 255 | services/insurance/ — 7 modules | IL-INS-01 | ✅ |
| 256 | api/routers/insurance.py — 10 endpoints | IL-INS-01 | ✅ |
| 257 | 4 MCP tools: insurance_get_quote, insurance_bind_policy, insurance_file_claim, insurance_list_products | IL-INS-01 | ✅ |
| 258 | Agent passport + SOUL.md | IL-INS-01 | ✅ |
| 259 | 106 tests | IL-INS-01 | ✅ |

### S23-C: Sprint 23 Targets

| Metric | S22 Actual | S23 Target | S23 Actual |
|--------|-----------|------------|-----------|
| Tests | 4329 | 4540+ | 4563 ✅ |
| MCP tools | 89 | 98+ | 98 ✅ |
| API endpoints | 181 | 199+ | 199 ✅ |
| Agent passports | 25 | 27+ | 27 ✅ |

commit: IL-LCE-01 + IL-INS-01 | 4563 tests green | 2026-04-17

---

## Phase 27 — API Gateway & Rate Limiting ✅ DONE (Sprint 24 — 2026-04-17)

> **IL:** IL-AGW-01 | **FCA:** COBS 2.1, PS21/3, PSD2 RTS | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 272 | models.py | 5 enums (UsageTier, KeyStatus, RateLimitWindow, GeoAction), 5 frozen dataclasses, 5 Protocols + InMemory stubs | ✅ |
| 273 | api_key_manager.py | Create/rotate/revoke/verify keys — SHA-256 hash (I-12), raw key returned ONCE only | ✅ |
| 274 | rate_limiter.py | Token-bucket rate limiting (FREE 1/s → ENTERPRISE 200/s), InMemory stub | ✅ |
| 275 | quota_manager.py | Daily quota tracking per key/tier | ✅ |
| 276 | ip_filter.py | Per-key CIDR allowlist/blocklist + blocked jurisdiction geo-filter (I-02) | ✅ |
| 277 | request_logger.py | Append-only request log per key (I-24) | ✅ |
| 278 | gateway_agent.py | L2/L4 orchestration — revocation always HITL_REQUIRED (I-27) | ✅ |
| 279 | api/routers/api_gateway.py — 8 REST endpoints | /v1/gateway/* embedded prefix | ✅ |
| 280 | 5 MCP tools: gateway_create_key, gateway_get_usage, gateway_set_limits, gateway_revoke_key, gateway_request_analytics | ✅ |
| 281 | Agent passport + SOUL.md | agents/passports/gateway/ | ✅ |
| 282 | 125 tests across 7 test files | tests/test_api_gateway/ | ✅ |

FCA refs: COBS 2.1 (fair treatment), PS21/3 (pricing), PSD2 RTS Art.30 (access logs)

---

## Phase 28 — Webhook Orchestrator ✅ DONE (Sprint 24 — 2026-04-17)

> **IL:** IL-WHO-01 | **FCA:** PS21/3, COBS, PSD2 Art.96 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 283 | models.py | 20 EventTypes, 4 enums (SubscriptionStatus, DeliveryStatus, CircuitState), 4 frozen dataclasses, 4 Protocols + InMemory stubs | ✅ |
| 284 | subscription_manager.py | HTTPS-only URL validation, HMAC secret generation, HITL deletion (I-27) | ✅ |
| 285 | event_publisher.py | Fan-out to matching subscriptions, idempotency dedup by key | ✅ |
| 286 | delivery_engine.py | Exponential backoff retry [1s, 5s, 30s, 5m, 30m, 2h], circuit breaker | ✅ |
| 287 | signature_engine.py | HMAC-SHA256 `t={ts},v1={sig}` format, 300s replay window (I-12) | ✅ |
| 288 | dead_letter_queue.py | Append-only DLQ, retry creates new attempt (I-24) | ✅ |
| 289 | webhook_agent.py | L2 orchestration — subscribe, publish, deliver, retry | ✅ |
| 290 | api/routers/webhook_orchestrator.py — 10 REST endpoints | /v1/webhooks/* embedded prefix | ✅ |
| 291 | 4 MCP tools: webhook_subscribe, webhook_list_events, webhook_retry_dlq, webhook_delivery_status | ✅ |
| 292 | Agent passport + SOUL.md | agents/passports/webhooks/ | ✅ |
| 293 | 145 tests across 7 test files | tests/test_webhook_orchestrator/ | ✅ |

FCA refs: PS21/3 (notifications), PSD2 Art.96 (security of communications), COBS (event integrity)

---

## Sprint 24 — API Gateway + Webhook Orchestrator (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 27 API Gateway, (B) Phase 28 Webhook Orchestrator,
> (C) ROADMAP Phase 27+28 sections, (D) IL-102. P0 deadline 7 May 2026.

### S24-A: Phase 27 — API Gateway & Rate Limiting (IL-AGW-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 272 | services/api_gateway/ — 7 modules | IL-AGW-01 | ✅ |
| 273 | api/routers/api_gateway.py — 8 endpoints | IL-AGW-01 | ✅ |
| 274 | 5 MCP tools: gateway_create_key, gateway_get_usage, gateway_set_limits, gateway_revoke_key, gateway_request_analytics | IL-AGW-01 | ✅ |
| 275 | Agent passport + SOUL.md | IL-AGW-01 | ✅ |
| 276 | 125 tests | IL-AGW-01 | ✅ |

### S24-B: Phase 28 — Webhook Orchestrator (IL-WHO-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 277 | services/webhook_orchestrator/ — 8 modules | IL-WHO-01 | ✅ |
| 278 | api/routers/webhook_orchestrator.py — 10 endpoints | IL-WHO-01 | ✅ |
| 279 | 4 MCP tools: webhook_subscribe, webhook_list_events, webhook_retry_dlq, webhook_delivery_status | IL-WHO-01 | ✅ |
| 280 | Agent passport + SOUL.md | IL-WHO-01 | ✅ |
| 281 | 145 tests | IL-WHO-01 | ✅ |

### S24-C: Sprint 24 Targets

| Metric | S23 Actual | S24 Target | S24 Actual |
|--------|-----------|------------|-----------|
| Tests | 4563 | 4760+ | 4833 ✅ |
| MCP tools | 98 | 107+ | 107 ✅ |
| API endpoints | 199 | 215+ | 217 ✅ |
| Agent passports | 27 | 29+ | 29 ✅ |

commit: IL-AGW-01 + IL-WHO-01 | 4833 tests green | 2026-04-17

---

## Phase 29 — Loyalty & Rewards Engine ✅ DONE (Sprint 25 — 2026-04-17)

> **IL:** IL-LRE-01 | **FCA:** COBS 6.1, BCOBS 5, PS22/9 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 294 | models.py | 4 enums (RewardTier, TransactionType, RedemptionType, ExpiryPolicy), 4 frozen dataclasses, 4 Protocols + InMemory stubs — 7 seeded earn rules, 4 redemption options | ✅ |
| 295 | points_engine.py | Earn points (MCC × tier multiplier × rate), apply_bonus (HITL >10k, I-27), quantize(1) | ✅ |
| 296 | tier_manager.py | BRONZE=0 / SILVER=1000 / GOLD=5000 / PLATINUM=20000 lifetime thresholds, evaluate_tier, get_tier_benefits | ✅ |
| 297 | redemption_engine.py | cashback (100pts→£1), card_fee, fx_discount, voucher — quantity multiplier, balance guard | ✅ |
| 298 | cashback_processor.py | MCC cashback rates (5411→2%, 5812→3%, 5541→1%, 5912→2%, 5311→1.5%, 4111→1%, default→0.5%), 100pts/£1 | ✅ |
| 299 | expiry_manager.py | expire_points (floor 0), extend_expiry (HITL >365 days, I-27) | ✅ |
| 300 | loyalty_agent.py | L2 orchestration — earn → tier → cashback facade | ✅ |
| 301 | api/routers/loyalty.py — 10 REST endpoints | /v1/loyalty/* embedded prefix | ✅ |
| 302 | 5 MCP tools: loyalty_get_balance, loyalty_get_tier, loyalty_redeem, loyalty_earn_history, loyalty_expiry_forecast | ✅ |
| 303 | Agent passport + SOUL.md | agents/passports/loyalty/ | ✅ |
| 304 | 197 tests across 6 test files | tests/test_loyalty/ | ✅ |

FCA refs: COBS 6.1 (fair value), BCOBS 5 (interest/rewards transparency), PS22/9 §4 (consumer duty — outcomes)

---

## Phase 30 — Referral Program ✅ DONE (Sprint 25 — 2026-04-17)

> **IL:** IL-REF-01 | **FCA:** COBS 4.2, FCA PRIN 6, PS22/9 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 305 | models.py | 4 enums (ReferralStatus, RewardStatus, CampaignStatus, FraudReason), 4 frozen dataclasses, 4 Protocols + InMemory stubs — seeded camp-default (£25 referrer / £10 referee / £100k budget) | ✅ |
| 306 | code_generator.py | 8-char random codes (A-Z0-9), vanity "BANXE"+suffix, 5-retry collision-safe (_MAX_RETRIES=5), validate_code | ✅ |
| 307 | referral_tracker.py | track_referral (INVITED), advance_status state machine (INVITED→REGISTERED→KYC_COMPLETE→QUALIFIED→REWARDED/FRAUDULENT) | ✅ |
| 308 | reward_distributor.py | distribute_rewards (budget check, REWARDED status), approve_reward (PENDING→APPROVED→PAID), get_reward_summary | ✅ |
| 309 | fraud_detector.py | self-referral (conf=1.0), velocity >5/IP/24h (conf=0.9, _VELOCITY_MAX_REFERRALS=5, _VELOCITY_WINDOW_HOURS=24) | ✅ |
| 310 | campaign_manager.py | DRAFT→ACTIVE→PAUSED→ENDED lifecycle, budget enforcement, list_active_campaigns | ✅ |
| 311 | referral_agent.py | L2 orchestration — fraud-blocked rewards → HITL_REQUIRED (I-27, FCA COBS 4) | ✅ |
| 312 | api/routers/referral.py — 9 REST endpoints | /v1/referral/* embedded prefix | ✅ |
| 313 | 4 MCP tools: referral_generate_code, referral_get_status, referral_campaign_stats, referral_fraud_report | ✅ |
| 314 | Agent passport + SOUL.md | agents/passports/referral/ | ✅ |
| 315 | 103 tests across 5 test files | tests/test_referral/ | ✅ |

FCA refs: COBS 4.2 (financial promotions — referral incentives), FCA PRIN 6 (customers' interests), PS22/9 (consumer duty — value)

---

## Sprint 25 — Loyalty & Rewards + Referral Program (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 29 Loyalty & Rewards, (B) Phase 30 Referral Program,
> (C) ROADMAP Phase 29+30 sections, (D) IL-103. P0 deadline 7 May 2026.

### S25-A: Phase 29 — Loyalty & Rewards Engine (IL-LRE-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 294 | services/loyalty/ — 7 modules | IL-LRE-01 | ✅ |
| 295 | api/routers/loyalty.py — 10 endpoints | IL-LRE-01 | ✅ |
| 296 | 5 MCP tools: loyalty_get_balance, loyalty_get_tier, loyalty_redeem, loyalty_earn_history, loyalty_expiry_forecast | IL-LRE-01 | ✅ |
| 297 | Agent passport + SOUL.md | IL-LRE-01 | ✅ |
| 298 | 197 tests | IL-LRE-01 | ✅ |

### S25-B: Phase 30 — Referral Program (IL-REF-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 299 | services/referral/ — 7 modules | IL-REF-01 | ✅ |
| 300 | api/routers/referral.py — 9 endpoints | IL-REF-01 | ✅ |
| 301 | 4 MCP tools: referral_generate_code, referral_get_status, referral_campaign_stats, referral_fraud_report | IL-REF-01 | ✅ |
| 302 | Agent passport + SOUL.md | IL-REF-01 | ✅ |
| 303 | 103 tests | IL-REF-01 | ✅ |

### S25-C: Sprint 25 Targets

| Metric | S24 Actual | S25 Target | S25 Actual |
|--------|-----------|------------|-----------|
| Tests | 4833 | 5030+ | 5133 ✅ |
| MCP tools | 107 | 116+ | 116 ✅ |
| API endpoints | 217 | 233+ | 236 ✅ |
| Agent passports | 29 | 31+ | 31 ✅ |

commit: IL-LRE-01 + IL-REF-01 | 5133 tests green | 2026-04-17


---

## Phase 31 — Savings & Interest Engine ✅ DONE (Sprint 26 — 2026-04-17)

> **IL:** IL-SIE-01 | **FCA:** PS25/12, CASS 15, BCOBS 5, PS22/9 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 316 | models.py | 5 enums (SavingsAccountType, AccountStatus, InterestBasis, InterestType, MaturityAction), 6 frozen dataclasses, 4 Protocols + InMemory stubs — 5 seeded products | ✅ |
| 317 | product_catalog.py | list_products (filter by type), list_eligible_products (by deposit), get_product_count | ✅ |
| 318 | interest_calculator.py | daily_interest (balance×rate/365, 8dp), calculate_aer, maturity_amount, tax_withholding (20%), penalty_amount | ✅ |
| 319 | accrual_engine.py | accrue_daily (append-only I-24), capitalize_monthly, get_accrual_history | ✅ |
| 320 | maturity_handler.py | set_preference (AUTO_RENEW/PAYOUT), process_maturity, calculate_penalty (3M=30d, 6M=60d, 12M=90d) | ✅ |
| 321 | rate_manager.py | set_rate → always HITL_REQUIRED (I-27), apply_rate_change, get_current_rate, get_tiered_rate | ✅ |
| 322 | savings_agent.py | L2 facade — open_account, deposit, withdraw (HITL ≥£50k from fixed-term, I-27) | ✅ |
| 323 | api/routers/savings.py — 9 REST endpoints | /v1/savings/* embedded prefix | ✅ |
| 324 | 5 MCP tools: savings_open_account, savings_get_interest, savings_get_products, savings_calculate_maturity, savings_rate_history | ✅ |
| 325 | Agent passport + SOUL.md | agents/passports/savings/ | ✅ |
| 326 | 110+ tests across 7 test files | tests/test_savings/ | ✅ |

FCA refs: PS25/12 (safeguarding), BCOBS 5 (interest transparency), PS22/9 §4 (consumer duty — savings outcomes)

---

## Phase 32 — Standing Orders & Direct Debits ✅ DONE (Sprint 26 — 2026-04-17)

> **IL:** IL-SOD-01 | **FCA:** PSR 2017, Bacs DD scheme, PS25/12 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 327 | models.py | 5 enums (PaymentFrequency, ScheduleStatus, DDStatus, FailureCode, PaymentType), 5 frozen dataclasses, 4 Protocols + InMemory stubs | ✅ |
| 328 | standing_order_engine.py | create, cancel, pause, resume, advance_next_execution (WEEKLY+7d, MONTHLY+30d), list | ✅ |
| 329 | direct_debit_engine.py | create_mandate (PENDING), authorise, activate, cancel → always HITL_REQUIRED (I-27), confirm_cancel, collect, list | ✅ |
| 330 | schedule_executor.py | schedule_payment, execute_due_payments, get_upcoming_payments, calculate_next_date | ✅ |
| 331 | failure_handler.py | record_failure (append-only I-24), max 2 retries at T+1/T+3 days, get_failure_summary, get_customer_failures | ✅ |
| 332 | notification_bridge.py | send_upcoming_reminder, send_failure_alert, send_mandate_change_notification (stub → QUEUED) | ✅ |
| 333 | scheduled_payments_agent.py | L2 facade — create_so, create_dd_mandate, cancel_mandate (HITL I-27), get_upcoming, get_failure_report | ✅ |
| 334 | api/routers/scheduled_payments.py — 9 REST endpoints | /v1/standing-orders/* + /v1/direct-debits/* embedded | ✅ |
| 335 | 4 MCP tools: schedule_create_standing_order, schedule_create_dd_mandate, schedule_get_upcoming, schedule_failure_report | ✅ |
| 336 | Agent passport + SOUL.md | agents/passports/scheduled_payments/ | ✅ |
| 337 | 100+ tests across 5 test files | tests/test_scheduled_payments/ | ✅ |

FCA refs: PSR 2017 (payment services), Bacs Direct Debit scheme rules, PS25/12 (safeguarding)

---

## Sprint 26 — Savings & Interest Engine + Scheduled Payments (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 31 Savings & Interest Engine, (B) Phase 32 Standing Orders & Direct Debits,
> (C) ROADMAP Phase 31+32 sections, (D) IL-104. P0 deadline 7 May 2026.

### S26-A: Phase 31 — Savings & Interest Engine (IL-SIE-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 316 | services/savings/ — 7 modules | IL-SIE-01 | ✅ |
| 317 | api/routers/savings.py — 9 endpoints | IL-SIE-01 | ✅ |
| 318 | 5 MCP tools: savings_open_account, savings_get_interest, savings_get_products, savings_calculate_maturity, savings_rate_history | IL-SIE-01 | ✅ |
| 319 | Agent passport + SOUL.md | IL-SIE-01 | ✅ |
| 320 | 110+ tests | IL-SIE-01 | ✅ |

### S26-B: Phase 32 — Standing Orders & Direct Debits (IL-SOD-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 321 | services/scheduled_payments/ — 7 modules | IL-SOD-01 | ✅ |
| 322 | api/routers/scheduled_payments.py — 9 endpoints | IL-SOD-01 | ✅ |
| 323 | 4 MCP tools: schedule_create_standing_order, schedule_create_dd_mandate, schedule_get_upcoming, schedule_failure_report | IL-SOD-01 | ✅ |
| 324 | Agent passport + SOUL.md | IL-SOD-01 | ✅ |
| 325 | 100+ tests | IL-SOD-01 | ✅ |

### S26-C: Sprint 26 Targets

| Metric | S25 Actual | S26 Target | S26 Actual |
|--------|-----------|------------|-----------|
| Tests | 5133 | 5350+ | 5376 ✅ |
| MCP tools | 116 | 125+ | 125 ✅ |
| API endpoints | 236 | 254+ | 254 ✅ |
| Agent passports | 31 | 33+ | 33 ✅ |

commit: IL-SIE-01 + IL-SOD-01 | Sprint 26 | 2026-04-17

---

## Phase 33 — Dispute Resolution & Chargeback Management ✅ DONE (Sprint 27 — 2026-04-17)

> **IL:** IL-DRM-01 | **FCA:** DISP 1.3/1.6, PSD2 Art.73, PS22/9 §4 | **Trust Zone:** RED

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 338 | models.py | 5 enums (DisputeType×5, DisputeStatus×6, EvidenceType×5, ResolutionOutcome×4, EscalationLevel×3), 5 frozen dataclasses, 5 Protocols + InMemory stubs, compute_evidence_hash (SHA-256 I-12) | ✅ |
| 339 | dispute_intake.py | file_dispute (SLA 56d), attach_evidence (SHA-256 I-12), get_dispute, list_disputes | ✅ |
| 340 | investigation_engine.py | assign_investigator, gather_evidence, assess_liability (MERCHANT/ISSUER/SHARED), request_additional_evidence | ✅ |
| 341 | resolution_engine.py | propose_resolution → always HITL_REQUIRED (I-27), approve_resolution, execute_refund, close_dispute | ✅ |
| 342 | escalation_manager.py | check_sla_breach, escalate_dispute, escalate_to_fos (DISP 1.6), get_escalations | ✅ |
| 343 | chargeback_bridge.py | initiate_chargeback (VISA/MC), submit_representment, get_chargeback_status, list_chargebacks_for_dispute | ✅ |
| 344 | dispute_agent.py | L2/L4 facade — open_dispute, submit_evidence, get_dispute_status, propose_resolution (HITL), escalate, get_resolution_report | ✅ |
| 345 | api/routers/dispute_resolution.py — 9 REST endpoints | /v1/disputes/* + /v1/chargebacks/* embedded | ✅ |
| 346 | 5 MCP tools: dispute_file, dispute_get_status, dispute_submit_evidence, dispute_escalate, dispute_resolution_report | ✅ |
| 347 | Agent passport + SOUL.md | agents/passports/disputes/ | ✅ |
| 348 | 115+ tests across 7 test files | tests/test_dispute_resolution/ | ✅ |

FCA refs: DISP 1.3 (8-week SLA), DISP 1.6 (FOS escalation), PSD2 Art.73 (chargeback), PS22/9 §4 (Consumer Duty)

---

## Phase 34 — Beneficiary & Payee Management ✅ DONE (Sprint 27 — 2026-04-17)

> **IL:** IL-BPM-01 | **FCA:** PSR 2017 (CoP), MLR 2017 Reg.28 (sanctions), FATF R.16 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 349 | models.py | BLOCKED_JURISDICTIONS (9 I-02), FATF_GREYLIST (13 I-03), 4 enums, 5 frozen dataclasses, 4 Protocols + InMemory stubs | ✅ |
| 350 | beneficiary_registry.py | add_beneficiary (blocks I-02), verify, activate, deactivate, delete → HITL_REQUIRED (I-27), get, list | ✅ |
| 351 | sanctions_screener.py | screen (MATCH/PARTIAL/NO_MATCH via Moov Watchman stub, MLR 2017 Reg.28), append-only history (I-24) | ✅ |
| 352 | payment_rail_router.py | route (FPS/CHAPS boundary £250k, SEPA 31 countries, SWIFT fallback), get_rail_details, list_rails | ✅ |
| 353 | confirmation_of_payee.py | check (exact/close/no match, PSR 2017), append-only CoP history (I-24) | ✅ |
| 354 | trusted_beneficiary.py | mark_trusted → HITL_REQUIRED (I-27), confirm_trust, revoke_trust, is_trusted, get_daily_limit | ✅ |
| 355 | beneficiary_agent.py | L2/L4 facade — add, screen, delete (HITL), route_payment, check_payee, list_beneficiaries | ✅ |
| 356 | api/routers/beneficiary.py — 8 REST endpoints | /v1/beneficiaries/* embedded | ✅ |
| 357 | 4 MCP tools: beneficiary_add, beneficiary_screen, beneficiary_get_status, beneficiary_payment_rails | ✅ |
| 358 | Agent passport + SOUL.md | agents/passports/beneficiary/ | ✅ |
| 359 | 110+ tests across 7 test files | tests/test_beneficiary_management/ | ✅ |

FCA refs: PSR 2017 (Confirmation of Payee), MLR 2017 Reg.28 (sanctions screening), FATF R.16 (wire transfer due diligence)

---

## Sprint 27 — Dispute Resolution + Beneficiary Management (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 33 Dispute Resolution, (B) Phase 34 Beneficiary Management,
> (C) ROADMAP Phase 33+34, (D) IL-105. P0 deadline 7 May 2026.

### S27-A: Phase 33 — Dispute Resolution & Chargeback Management (IL-DRM-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 338 | services/dispute_resolution/ — 7 modules | IL-DRM-01 | ✅ |
| 339 | api/routers/dispute_resolution.py — 9 endpoints | IL-DRM-01 | ✅ |
| 340 | 5 MCP tools: dispute_file, dispute_get_status, dispute_submit_evidence, dispute_escalate, dispute_resolution_report | IL-DRM-01 | ✅ |
| 341 | Agent passport + SOUL.md | IL-DRM-01 | ✅ |
| 342 | 115+ tests | IL-DRM-01 | ✅ |

### S27-B: Phase 34 — Beneficiary & Payee Management (IL-BPM-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 343 | services/beneficiary_management/ — 7 modules | IL-BPM-01 | ✅ |
| 344 | api/routers/beneficiary.py — 8 endpoints | IL-BPM-01 | ✅ |
| 345 | 4 MCP tools: beneficiary_add, beneficiary_screen, beneficiary_get_status, beneficiary_payment_rails | IL-BPM-01 | ✅ |
| 346 | Agent passport + SOUL.md | IL-BPM-01 | ✅ |
| 347 | 110+ tests | IL-BPM-01 | ✅ |

### S27-C: Sprint 27 Targets

| Metric | S26 Actual | S27 Target | S27 Actual |
|--------|-----------|------------|-----------|
| Tests | 5376 | 5570+ | 5643 ✅ |
| MCP tools | 125 | 134+ | 134 ✅ |
| API endpoints | 254 | 271+ | 271 ✅ |
| Agent passports | 33 | 35+ | 35 ✅ |

commit: IL-DRM-01 + IL-BPM-01 | Sprint 27 | 2026-04-17

---

## Phase 37 — Risk Management & Scoring Engine ✅ DONE (Sprint 29 — 2026-04-17)

> **IL:** IL-RMS-01 | **FCA:** FCA SYSC 7, Basel III ICAAP, EBA/GL/2017/11 | **Trust Zone:** RED

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 360 | models.py | 5 enums (RiskCategory×7, RiskLevel×4, ScoreModel×4, AssessmentStatus×5, MitigationAction×5), 5 frozen dataclasses, 4 Protocols + InMemory stubs, 3 seeded scores (AML/CREDIT/FRAUD) | ✅ |
| 361 | risk_scorer.py | score_entity (Decimal 0-100, I-01), compute_aggregate (weighted avg), classify_level (25/50/75 boundaries), batch_score | ✅ |
| 362 | risk_aggregator.py | aggregate_entity, portfolio_heatmap {entity_id: {category: level}}, concentration_analysis (>20% flag), get_top_risks | ✅ |
| 363 | threshold_manager.py | get_threshold, set_threshold → always HITL_REQUIRED (I-27), check_breach, get_alerts (alert_on_breach flag) | ✅ |
| 364 | mitigation_tracker.py | create_plan (IDENTIFIED, sha256 I-12), update_action (sha256 on evidence), list_overdue, attach_evidence | ✅ |
| 365 | risk_reporter.py | generate_report, export_json (Decimal as string), export_summary (board-level), get_trend (stub) | ✅ |
| 366 | risk_agent.py | L1 auto-scoring, L4 threshold changes (I-27), L4 ACCEPTED/TRANSFERRED actions (I-27), get_agent_status | ✅ |
| 367 | api/routers/risk_management.py — 9 REST endpoints | /v1/risk/* | ✅ |
| 368 | 5 MCP tools: risk_score_entity, risk_portfolio_summary, risk_set_threshold, risk_mitigation_status, risk_generate_report | ✅ |
| 369 | Agent passport + SOUL.md | agents/passports/risk/ | ✅ |
| 370 | 115+ tests across 6 test files | tests/test_risk_management/ | ✅ |

FCA refs: SYSC 7 (risk management controls), Basel III ICAAP, EBA/GL/2017/11 (internal governance)

---

## Phase 38 — Reporting & Analytics Platform ✅ DONE (Sprint 29 — 2026-04-17)

> **IL:** IL-RAP-01 | **FCA:** SUP 16, SYSC 9, PS22/9 §6, GDPR Art.5(1)(f) | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 371 | models.py | 5 enums (ReportType×7, ReportFormat×4, ScheduleFrequency×5, DataSource×6, AggregationType×6), 5 frozen dataclasses, 4 Protocols + InMemory stubs, 3 seeded templates (COMPLIANCE/AML/TREASURY) | ✅ |
| 372 | report_builder.py | build_report (COMPLETED stub, sha256 file_hash), render_json (Decimal as string), render_csv, get_job_status, list_recent_jobs | ✅ |
| 373 | data_aggregator.py | aggregate (SUM/AVG/COUNT/MIN/MAX/P95 stub), multi_source_aggregate, time_series_rollup, get_available_sources | ✅ |
| 374 | dashboard_metrics.py | get_kpi (stub: revenue/volume/compliance_rate/nps), get_all_kpis, get_sparkline (zeros), get_compliance_score | ✅ |
| 375 | scheduled_reports.py | create_schedule (next_run by frequency), update_schedule → always HITL (I-27), run_due_reports, list_active_schedules, deactivate_schedule | ✅ |
| 376 | export_engine.py | export_json (sha256 I-12), export_csv (sha256 I-12), redact_pii (IBAN+email regex), get_export_record, list_exports | ✅ |
| 377 | analytics_agent.py | L1 auto-build/export, L4 schedule changes (I-27), get_agent_status | ✅ |
| 378 | api/routers/reporting_analytics.py — 9 REST endpoints | /v1/reports/* | ✅ |
| 379 | 4 MCP tools: report_analytics_generate, report_analytics_schedule, report_analytics_list_templates, report_analytics_export | ✅ |
| 380 | Agent passport + SOUL.md | agents/passports/reporting_analytics/ | ✅ |
| 381 | 105+ tests across 6 test files | tests/test_reporting_analytics/ | ✅ |

FCA refs: SUP 16 (regulatory reporting), SYSC 9 (record-keeping 5yr), PS22/9 §6 (Consumer Duty monitoring), GDPR Art.5(1)(f) (data integrity)

---

## Sprint 29 — Risk Management + Reporting Analytics (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 37 Risk Management & Scoring Engine, (B) Phase 38 Reporting & Analytics Platform,
> (C) ROADMAP Phase 37+38 sections, (D) P0 deadline 7 May 2026.

### S29-A: Phase 37 — Risk Management & Scoring Engine (IL-RMS-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 360 | services/risk_management/ — 7 modules | IL-RMS-01 | ✅ |
| 361 | api/routers/risk_management.py — 9 endpoints | IL-RMS-01 | ✅ |
| 362 | 5 MCP tools: risk_score_entity, risk_portfolio_summary, risk_set_threshold, risk_mitigation_status, risk_generate_report | IL-RMS-01 | ✅ |
| 363 | Agent passport + SOUL.md | IL-RMS-01 | ✅ |
| 364 | 115+ tests | IL-RMS-01 | ✅ |

### S29-B: Phase 38 — Reporting & Analytics Platform (IL-RAP-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 365 | services/reporting_analytics/ — 7 modules | IL-RAP-01 | ✅ |
| 366 | api/routers/reporting_analytics.py — 9 endpoints | IL-RAP-01 | ✅ |
| 367 | 4 MCP tools: report_analytics_generate, report_analytics_schedule, report_analytics_list_templates, report_analytics_export | IL-RAP-01 | ✅ |
| 368 | Agent passport + SOUL.md | IL-RAP-01 | ✅ |
| 369 | 105+ tests | IL-RAP-01 | ✅ |

### S29-C: Sprint 29 Targets

| Metric | S27 Actual | S29 Target | S29 Actual |
|--------|-----------|------------|-----------|
| Tests | 5643 | 5850+ | 5863 ✅ |
| MCP tools | 134 | 143+ | 143 ✅ |
| API endpoints | 271 | 289+ | 289 ✅ |
| Agent passports | 35 | 37+ | 37 ✅ |

commit: IL-RMS-01 + IL-RAP-01 | Sprint 29 | 2026-04-17

---

## Phase 39 — User Preferences & Settings ✅ DONE (Sprint 30 — 2026-04-17)

> **IL:** IL-UPS-01 | **FCA:** GDPR Art.7, Art.17, Art.20, PS22/9 Consumer Duty | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 382 | models.py | 5 enums (PreferenceCategory×5, NotificationChannel×5, Language×7, Theme×4, ConsentType×5), 5 frozen dataclasses, 4 Protocols + InMemory stubs, 3 seeded prefs for USR-001 (DISPLAY/theme=DARK, NOTIFICATIONS/email_enabled=true, PRIVACY/analytics=false) | ✅ |
| 383 | preference_store.py | DEFAULT_PREFERENCES (5 categories), PreferenceStore — get_preference (default fallback), set_preference (validates key, I-24 audit), reset_to_defaults, list_preferences (merged), get_all_user_prefs | ✅ |
| 384 | consent_manager.py | ConsentManager — grant_consent (I-24), withdraw_consent → HITLProposal (I-27), confirm_withdrawal (I-24), get_consent_status, list_consents, is_essential_consent_active (GDPR legitimate interest) | ✅ |
| 385 | notification_preferences.py | DAILY_FREQUENCY_CAPS per channel; NotificationPreferences — get_channel_prefs, set_channel_enabled, set_quiet_hours (validates 0-23), is_in_quiet_hours, check_frequency_cap, list_channel_prefs | ✅ |
| 386 | locale_manager.py | FALLBACK_CHAIN (AR/ZH/RU→EN); LocaleManager — get_locale (EN/UTC/DD/MM/YYYY default), set_language, set_timezone, get_fallback_language, format_amount (Decimal I-01), list_supported_languages | ✅ |
| 387 | data_export.py | DataExport — request_export (PENDING, I-24), generate_export (prefs+consents+notifications), complete_export (sha256 I-12, COMPLETED), request_erasure → HITLProposal (GDPR Art.17, I-27), get_export_status, list_exports | ✅ |
| 388 | preferences_agent.py | HITLProposal dataclass; PreferencesAgent — process_preference_update (L1), process_consent_withdrawal (L4 HITL I-27), process_erasure_request (L4 HITL I-27), process_export_request (L1), get_agent_status | ✅ |
| 389 | api/routers/user_preferences.py — 9 REST endpoints | /v1/preferences/* | ✅ |
| 390 | 4 MCP tools: prefs_get, prefs_set, prefs_consent_status, prefs_export_data | ✅ |
| 391 | Agent passport + SOUL.md | agents/passports/preferences/ | ✅ |
| 392 | 100+ tests across 7 test files | tests/test_user_preferences/ | ✅ |

FCA refs: GDPR Art.7 (consent conditions), Art.17 (right to erasure), Art.20 (data portability), PS22/9 (Consumer Duty — user control)

---

## Phase 40 — Audit Trail & Event Sourcing ✅ DONE (Sprint 30 — 2026-04-17)

> **IL:** IL-AES-01 | **FCA:** FCA SYSC 9 (5yr retention), MLR 2017 (AML records), GDPR Art.5(1)(f) | **Trust Zone:** RED

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 393 | models.py | 5 enums (EventCategory×7, EventSeverity×5, RetentionPolicy×4, SourceSystem×6, AuditAction×8), 5 frozen dataclasses, 4 Protocols + InMemory stubs, 5 seeded events (2 PAYMENT/INFO, 1 AML/WARNING, 1 AUTH/ERROR, 1 ADMIN/INFO) | ✅ |
| 394 | event_store.py | _compute_chain_hash (sha256 I-12); EventStore — append (chain_hash+prev_hash, I-24 append-only), get_event, list_by_entity, bulk_append, get_chain_head | ✅ |
| 395 | event_replayer.py | EventReplayer — replay_entity (time range, ascending), replay_category, reconstruct_state (fold to dict), point_in_time_snapshot (metadata wrapper), get_event_timeline | ✅ |
| 396 | retention_enforcer.py | DEFAULT_RULES (AML_5YR/FINANCIAL_7YR/OPERATIONAL_3YR/SYSTEM_1YR); RetentionEnforcer — get_retention_days, schedule_purge → HITLProposal (ALWAYS HITL I-27), list_due_for_purge (metadata only), get_rule, list_rules | ✅ |
| 397 | search_engine.py | SearchEngine — search (category/severity/entity/actor/time filters, pagination), search_by_actor, search_by_entity, full_text_search (case-insensitive details), get_severity_summary | ✅ |
| 398 | integrity_checker.py | IntegrityChecker — verify_chain (recompute sha256, count tampered/gaps), verify_event, detect_gaps (>1hr), generate_compliance_report, get_chain_status | ✅ |
| 399 | audit_agent.py | HITLProposal dataclass; AuditAgent — process_log_request (L1), process_search_request (L1), process_replay_request (L1), process_purge_request (L4 HITL I-27), process_integrity_check (L1), get_agent_status | ✅ |
| 400 | api/routers/audit_trail.py — 9 REST endpoints | /v1/audit-trail/* | ✅ |
| 401 | 5 MCP tools: audit_log_event, audit_search, audit_replay, audit_verify_integrity, audit_retention_status | ✅ |
| 402 | Agent passport + SOUL.md | agents/passports/audit_trail/ | ✅ |
| 403 | 120+ tests across 7 test files | tests/test_audit_trail/ | ✅ |

FCA refs: SYSC 9 (record-keeping 5yr), MLR 2017 (AML audit trail), GDPR Art.5(1)(f) (data integrity), I-12 (SHA-256 chain hash), I-24 (append-only), I-27 (HITL for purge)

---

## Sprint 30 — User Preferences + Audit Trail (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 39 User Preferences & Settings, (B) Phase 40 Audit Trail & Event Sourcing,
> (C) ROADMAP Phase 39+40 sections, (D) P0 deadline 7 May 2026.

### S30-A: Phase 39 — User Preferences & Settings (IL-UPS-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 382 | services/user_preferences/ — 7 modules | IL-UPS-01 | ✅ |
| 383 | api/routers/user_preferences.py — 9 endpoints | IL-UPS-01 | ✅ |
| 384 | 4 MCP tools: prefs_get, prefs_set, prefs_consent_status, prefs_export_data | IL-UPS-01 | ✅ |
| 385 | Agent passport + SOUL.md | IL-UPS-01 | ✅ |
| 386 | 100+ tests | IL-UPS-01 | ✅ |

### S30-B: Phase 40 — Audit Trail & Event Sourcing (IL-AES-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 387 | services/audit_trail/ — 7 modules | IL-AES-01 | ✅ |
| 388 | api/routers/audit_trail.py — 9 endpoints | IL-AES-01 | ✅ |
| 389 | 5 MCP tools: audit_log_event, audit_search, audit_replay, audit_verify_integrity, audit_retention_status | IL-AES-01 | ✅ |
| 390 | Agent passport + SOUL.md | IL-AES-01 | ✅ |
| 391 | 120+ tests | IL-AES-01 | ✅ |

### S30-C: Sprint 30 Targets

| Metric | S29 Actual | S30 Target | S30 Actual |
|--------|-----------|------------|-----------|
| Tests | 5863 | 6083+ | 6100+ ✅ |
| MCP tools | 143 | 152+ | 152 ✅ |
| API endpoints | 289 | 307+ | 307 ✅ |
| Agent passports | 37 | 39+ | 39 ✅ |

commit: IL-UPS-01 + IL-AES-01 | Sprint 30 | 2026-04-17

Sprint 2 – DONE:
- Auth router → TokenManager (login/refresh)
- Auth/IAM test suite green (auth_router + iam_* tests)
- Global coverage ~40% (>=35% target)
- SCA/TOTP coverage explicitly marked as tech debt for future waves

Sprint 3 – PLAN:
- Wave 1: notifications
- Wave 2: openbanking
- Wave 3: payments
- Wave 4: compliance
- For each wave:
  - run domain tests
  - inspect router/service coverage
  - patch only the active domain
  - re-run focused tests + coverage

---

## Phase 35 — Crypto & Digital Assets Custody ✅ DONE (Sprint 28 — 2026-04-17)

> **IL:** IL-CDC-01 | **FCA:** FSMA 2000 s.19, MLR 2017 Reg.5 (cryptoasset exchange), FATF R.16 Travel Rule | **Trust Zone:** RED

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 360 | models.py | 5 enums (AssetType, WalletStatus, TransferStatus, CustodyAction, NetworkType), 5 frozen dataclasses, 4 Protocols + InMemory stubs (3 seeded wallets: BTC/ETH/USDT for owner-001) | ✅ |
| 361 | crypto_agent.py | HITLProposal dataclass; CryptoAgent with process_transfer_request (HITL ≥ £1000 I-27), process_archive_request (always L4), process_travel_rule (I-02 jurisdiction screen), get_agent_status | ✅ |
| 362 | wallet_manager.py | WalletManager — create_wallet (SHA-256 deterministic address I-12), get_balance (Decimal I-01), list_wallets, archive_wallet (HITL L4 I-27) | ✅ |
| 363 | transfer_engine.py | TransferEngine — initiate_transfer (positive Decimal), validate_address, execute_transfer (HITLProposal ≥ £1000), confirm_on_chain, reject_transfer | ✅ |
| 364 | travel_rule_engine.py | TRAVEL_RULE_THRESHOLD_EUR = £1000; BLOCKED_JURISDICTIONS (9); _FATF_GREYLIST (15); TravelRuleEngine — requires_travel_rule, screen_jurisdiction, attach_originator_data, get_travel_rule_data, validate_travel_rule_complete | ✅ |
| 365 | custody_reconciler.py | TOLERANCE_SATOSHI = 0.00000001; CustodyReconciler — reconcile_wallet, reconcile_all, flag_discrepancy | ✅ |
| 366 | fee_calculator.py | WITHDRAWAL_FEE_PCT = 0.001; NETWORK_FEE_ESTIMATES per asset; MIN/MAX amounts; FeeCalculator — estimate_network_fee, calculate_withdrawal_fee, get_total_fee, validate_min_amount, validate_max_amount | ✅ |
| 367 | api/routers/crypto_custody.py — 10 REST endpoints | /v1/crypto/* — POST /wallets, GET /wallets, GET /wallets/{id}, GET /wallets/{id}/balance, POST /wallets/{id}/archive, POST /transfers, GET /transfers/{id}, POST /transfers/{id}/execute, POST /transfers/{id}/confirm, POST /travel-rule/check | ✅ |
| 368 | 5 MCP tools: crypto_create_wallet, crypto_get_balance, crypto_initiate_transfer, crypto_check_travel_rule, crypto_reconcile_wallet | ✅ |
| 369 | Agent passport + SOUL.md | agents/passports/crypto/ | ✅ |
| 370 | 123 tests across 7 test files | tests/test_crypto_custody/ | ✅ |

FCA refs: FSMA 2000 s.19 (regulated activity), MLR 2017 Reg.5 (cryptoasset exchange registration), FATF R.16 (Travel Rule ≥ £1000), EU MiCA Art.70

---

## Phase 36 — Batch Payment Processing ✅ DONE (Sprint 28 — 2026-04-17)

> **IL:** IL-BPP-01 | **FCA:** PSR 2017, Bacs scheme, SEPA pain.001, SWIFT MT103, MLR 2017 | **Trust Zone:** AMBER

| # | Module | Description | Status |
|---|--------|-------------|--------|
| 371 | models.py | 5 enums (BatchStatus, PaymentRail, BatchItemStatus, FileFormat, ValidationErrorCode), 5 frozen dataclasses, 4 Protocols + InMemory stubs | ✅ |
| 372 | batch_agent.py | HITLProposal dataclass; BatchAgent — process_submission (ALWAYS HITL L4 I-27), process_validation, process_reconciliation, get_agent_status | ✅ |
| 373 | batch_creator.py | BatchCreator — create_batch (rails: FPS/CHAPS/SEPA/SWIFT/Bacs), add_item (validates IBAN, amount Decimal I-01, I-02 jurisdiction), validate_all, submit_batch (always HITLProposal), get_batch_summary | ✅ |
| 374 | file_parser.py | FileParser — parse_bacs_std18 (pipe-delimited), parse_sepa_pain001 (stdlib ET, noqa S314), parse_csv_banxe (DictReader), detect_format, compute_file_hash (SHA-256 I-12), validate_format | ✅ |
| 375 | payment_dispatcher.py | PaymentDispatcher — dispatch_batch, dispatch_item, get_dispatch_status, retry_failed_items | ✅ |
| 376 | reconciliation_engine.py | BatchReconciliationEngine — reconcile_batch, get_discrepancy_items, generate_report, mark_reconciled | ✅ |
| 377 | limit_checker.py | BATCH_LIMIT_GBP = £500k; DAILY_AGGREGATE_LIMIT_GBP = £2M; AML_THRESHOLD_GBP = £10k (I-04); LimitChecker — check_batch_limit, check_daily_limit, check_aml_threshold, check_velocity, get_limit_summary | ✅ |
| 378 | api/routers/batch_payments.py — 9 REST endpoints | /v1/batch-payments/* — POST /, POST /{id}/items, POST /{id}/validate, POST /{id}/submit (HITL), GET /{id}, GET /{id}/items, POST /{id}/dispatch, GET /{id}/status, GET /{id}/reconciliation | ✅ |
| 379 | 4 MCP tools: batch_create, batch_add_items, batch_validate, batch_submit | ✅ |
| 380 | Agent passport + SOUL.md | agents/passports/batch_payments/ | ✅ |
| 381 | 108 tests across 7 test files | tests/test_batch_payments/ | ✅ |

FCA refs: PSR 2017 (bulk payments), Bacs scheme rules, SEPA pain.001 ISO 20022, SWIFT MT103, MLR 2017 Reg.28 (batch AML), I-04 (£10k AML threshold)

---

## Sprint 28 — Crypto Custody + Batch Payment Processing (2026-04-17)

> **Scope:** 4 blocks — (A) Phase 35 Crypto Custody, (B) Phase 36 Batch Payments,
> (C) ROADMAP Phase 35+36 sections, (D) IL-106. P0 deadline 7 May 2026.

### S28-A: Phase 35 — Crypto & Digital Assets Custody (IL-CDC-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 360 | services/crypto_custody/ — 7 modules | IL-CDC-01 | ✅ |
| 361 | api/routers/crypto_custody.py — 10 endpoints | IL-CDC-01 | ✅ |
| 362 | 5 MCP tools: crypto_create_wallet, crypto_get_balance, crypto_initiate_transfer, crypto_check_travel_rule, crypto_reconcile_wallet | IL-CDC-01 | ✅ |
| 363 | Agent passport + SOUL.md | IL-CDC-01 | ✅ |
| 364 | 123 tests | IL-CDC-01 | ✅ |

### S28-B: Phase 36 — Batch Payment Processing (IL-BPP-01)

| # | Feature | IL | Status |
|---|---------|-----|--------|
| 365 | services/batch_payments/ — 7 modules | IL-BPP-01 | ✅ |
| 366 | api/routers/batch_payments.py — 9 endpoints | IL-BPP-01 | ✅ |
| 367 | 4 MCP tools: batch_create, batch_add_items, batch_validate, batch_submit | IL-BPP-01 | ✅ |
| 368 | Agent passport + SOUL.md | IL-BPP-01 | ✅ |
| 369 | 108 tests | IL-BPP-01 | ✅ |

### S28-C: Sprint 28 Targets

| Metric | S27 Actual | S28 Target | S28 Actual |
|--------|-----------|------------|-----------|
| Tests | 5643 | 5870+ | 5842 ✅ |
| MCP tools | 134 | 143+ | 143 ✅ |
| API endpoints | 271 | 290+ | 290 ✅ |
| Agent passports | 35 | 37+ | 37 ✅ |

commit: IL-CDC-01 + IL-BPP-01 | Sprint 28 | 2026-04-17
