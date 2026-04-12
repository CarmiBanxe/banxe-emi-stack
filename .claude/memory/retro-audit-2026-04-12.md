---
name: IL-RETRO-01 — Retrospective Documentation Audit
description: Read-only audit of documentation gaps across git history, INSTRUCTION-LEDGER, MEMORY.md, .claude/memory, ADRs, rules, and docs/ as of 2026-04-12
type: project
---

# IL-RETRO-01 — Ретроспективный аудит документации

**Дата:** 2026-04-12
**Режим:** READ-ONLY (никакие файлы кроме этого отчёта не изменены)
**Период:** 2026-03-01 → 2026-04-12
**Репо:** banxe-emi-stack + banxe-architecture

---

## Методология

1. `git log --oneline --all --since="2026-03-01"` для обоих репо
2. Сопоставление коммитов с записями в INSTRUCTION-LEDGER (IL-001..IL-072)
3. Проверка наличия: MEMORY.md, .claude/memory/, docs/adr/, .claude/rules/, docs/

---

## Результаты

---

### A. Коммиты без записи в INSTRUCTION-LEDGER

#### A1. Именованные ILs — есть в коммитах, НЕТ в INSTRUCTION-LEDGER как numbered entries

| Коммит | IL-тикет | Описание | Масштаб | Нужная запись |
|--------|----------|----------|---------|---------------|
| `d39d709` | IL-SK-01 | Starter Kit merge — rules, commands, specs, GH Actions, templates | M | IL-073 или вписать в IL-045 |
| `b858855`, `91e2ed9`, `fbdb803`, `8688e74` | IL-MCP-01 | MCP Server — 6 tools, semgrep, soul, orchestrator, n8n, docker, grafana, dbt | XL | IL-074 |
| `5f132dd` | IL-ARL-01 | Agent Routing Layer — 3-tier LLM routing, 184 tests | L | IL-075 |
| `9b8fb48` | IL-D2C-01 | Design-to-Code Pipeline — Penpot MCP + AI scaffold, 207 tests | L | IL-076 |
| `3e592d0` | IL-ADDS-01 | AI-Driven Design System — DESIGN.md + component library + 3 modules, ~160 tests | L | IL-077 |
| `28c35cd` + ~40 commits | IL-SAF-01 | **Safeguarding Engine CASS 15** — полный микросервис (prompt 19), 8 API endpoints, 10 MCP tools, SQLAlchemy models, Alembic migrations | **XXL** | **IL-078** |

> **Критично:** IL-SAF-01 — это ~40 коммитов, полноценный микросервис, ни одной записи в INSTRUCTION-LEDGER.

#### A2. Gap в числовой последовательности

| Gap | Между | Что было |
|-----|-------|---------|
| **IL-027** | IL-026 и IL-028 | IL-026 = Consumer Duty deploy GMKtec; IL-028 = CASS 10A Resolution Pack. IL-027 не существует. |

#### A3. Архитектурные ILs (banxe-architecture commits) — не в INSTRUCTION-LEDGER

Коммиты в banxe-architecture ссылаются на IL-080..IL-089, но в INSTRUCTION-LEDGER нет `### IL-073` и выше:

| Коммит в arch | IL-ref | Описание |
|---------------|--------|---------|
| `ff49972` | IL-080 | JOB-DESCRIPTIONS.md — AI agents & human doubles |
| `e7ed422` | IL-081 | FEATURE-REGISTRY.md — 30 features |
| `ac7721d` | IL-082 | RELATIONSHIP-TREE.md — org relationships |
| `493bd3b` | IL-083 | ROADMAP.md — architecture phases |
| `3945cd2` | IL-084 | mkdocs.yml |
| `e27439e` | IL-085 | DEV-DOCUMENTATION-GUIDE.md |
| `9ce939e` | IL-086 | MkDocs GitHub Pages deploy workflow |
| `629eedc` | IL-087 | CHANGELOG-POLICY.md |
| `ac22c30` (emi) | IL-088 | auto-documentation pipeline prompt 18 |
| `50f9c60` (arch) | IL-089 | Phase 3.5 = IL-CKS-01 |

> **Вывод:** IL-073..IL-079 (для SK/MCP/ARL/D2C/ADDS/SAF + возможно других) и IL-080..IL-089 (arch docs) не зарегистрированы в INSTRUCTION-LEDGER. Счётчик фактически должен быть ~IL-089.

---

### B. Пробелы в MEMORY.md

#### B1. banxe-architecture/MEMORY.md

**Последнее обновление сегодня:** IL-BIOME-01 (2026-04-12).
Предыдущее содержимое охватывало Sprint 4-7 (banxe-architecture repo).

**Отсутствуют sprint/IL entries для banxe-emi-stack (крупные фичи):**

| Отсутствующая запись | Почему важно |
|----------------------|-------------|
| IL-SK-01 Starter Kit | Ввёл .claude/rules, .claude/commands, .semgrep — ключевая инфраструктура |
| IL-MCP-01 MCP Server | 6 инструментов, интеграция с orchestrator — это published API |
| IL-ARL-01 Agent Routing Layer | 3-tier routing, 184 tests, core AI infra |
| IL-D2C-01 Design-to-Code | Penpot+Mitosis pipeline, 207 tests |
| IL-ADDS-01 AI Design System | Component library, frontend-первый шаг |
| IL-SAF-01 Safeguarding Engine | CASS 15, ~40 commits, production microservice |
| IL-060..068 (8 ILs) | spec_first_auditor v2, UI blocks, ARL, quality gates, org, finance, AML |

#### B2. banxe-emi-stack/.claude/memory/

**Текущее состояние:**
```
MEMORY.md (индекс)
feedback_pytest_hook.md
project_adds.md    ✅
project_arl.md     ✅
project_cec.md     ✅
project_cks.md     ✅
project_d2c.md     ✅
project_rtm.md     ✅
quality_gates.md   ✅ (создан сегодня)
```

**Отсутствующие файлы:**

| Нужный файл | Для чего | IL |
|-------------|----------|-----|
| `project_safeguarding.md` | Safeguarding Engine CASS 15 — ~40 коммитов, production microservice (services/safeguarding-engine/) | IL-SAF-01 |
| `project_mcp.md` | MCP Server — banxe_mcp/server.py, 6 tools, orchestrator integration | IL-MCP-01 |
| `project_sk.md` | Starter Kit — .claude/rules/, .claude/commands/, .semgrep/, GitHub Actions templates | IL-SK-01 |

---

### C. Пробелы в .claude/rules/

**Текущее состояние:**
```
00-global.md, 10-backend-python.md, 20-api-contracts.md, 30-testing.md
40-docs.md, 60-migrations.md, 90-reporting.md, 95-incidents.md
agent-authority.md, compliance-boundaries.md, financial-invariants.md
git-workflow.md, infrastructure-utilization.md, quality-gates.md
security-policy.md, session-continuity.md
```

**Отсутствующие правила (нет покрытия для построенного):**

| Файл | Что должно быть | Триггер |
|------|----------------|--------|
| `50-frontend.md` | React/TypeScript правила: Biome config, Mitosis pipeline, компонентные паттерны, generated/ exclusions, Zustand store conventions | Добавлены frontend/ (IL-ADDS-01, IL-BIOME-01) |
| `70-mcp-tools.md` | MCP tool development rules: FastMCP patterns, naming conventions (`verb_noun`), обязательный audit trail в каждом tool, error handling, ClickHouse logging | MCP server built (IL-MCP-01), 5 наборов tools добавлено |
| `80-ai-agents.md` | AI agent dev rules: soul file structure, Protocol DI для agent ports, swarm patterns, HITL gates в agent code, orchestrator registration protocol | ARL (IL-ARL-01), CKS/CEC/RTM (IL-069..071) |

**Устаревшие записи в существующих rules:**
- `30-testing.md`: тест-счётчик "1 931 тестов" теперь в quality-gates.md, но в 30-testing.md нет упоминания InMemory stub pattern для агентов
- `90-reporting.md`: ссылается на `services/reporting/fin060_generator.py` — актуально. Но нет упоминания `services/safeguarding-engine/` reporting.

---

### D. Отсутствующие ADR

**Текущее состояние:** только ADR-001-biome-vs-eslint.md.

**Архитектурные решения без ADR в banxe-emi-stack/docs/adr/:**

| ADR | Решение | Где закреплено сейчас | Критичность |
|-----|---------|----------------------|-------------|
| ADR-002 | **ClickHouse как append-only audit log (5-year TTL)** | Invariant I-08, I-24 в financial-invariants.md | HIGH — финансовый audit |
| ADR-003 | **Midaz как Primary CBS** | banxe-architecture/ADR-013 — НЕ зеркалируется в emi-stack | HIGH — фундаментальный |
| ADR-004 | **FastMCP / MCP protocol для agent tooling** | Нигде, только код | HIGH — инфраструктура AI |
| ADR-005 | **Protocol DI pattern (typing.Protocol + InMemory stubs)** | .claude/rules/10-backend-python.md (упомянут) — не ADR | MEDIUM — ключевой архитектурный паттерн |
| ADR-006 | **WeasyPrint для FIN060 PDF generation** | docs/ARCHITECTURE-RECON.md (упомянут) | MEDIUM — FCA reporting |
| ADR-007 | **Decimal(Python) / Decimal(20,8)(SQL) для денег** | Invariant I-01 — не ADR | HIGH — финансовая корректность |
| ADR-008 | **FastAPI как web framework** | Нигде | MEDIUM — web infra |
| ADR-009 | **Blnk Finance для position tracking** | CLAUDE.md P0 Stack Map — не ADR | MEDIUM — recon infra |

---

### E. Пробелы в docs/

#### E1. Устаревшие документы

| Файл | Версия/дата | Последнее обновление | Что пропущено |
|------|------------|---------------------|---------------|
| `docs/API.md` | v0.7.0, 2026-04-07 | IL-017 (commit 630f647) | APIs с IL-046 по IL-072: Transaction Monitor (8 endpoints), Compliance KB API, Experiment Copilot API, Safeguarding Engine API (8 endpoints), MCP tools (25+ tools), ARL API |
| `docs/RUNBOOK.md` | 2026-04-07 | IL-017 (commit 630f647) | Operational procedures для: Transaction Monitor, Safeguarding Engine, MCP server restart, ClickHouse/Redis maintenance, Keycloak |
| `docs/ONBOARDING.md` | 2026-04-07 | IL-017 | New services (transaction_monitor, safeguarding-engine, compliance KB), pre-commit setup с Biome |

#### E2. Пустые placeholder-директории (только README.md)

| Директория | Что должно быть | Связанные IL |
|-----------|----------------|-------------|
| `docs/architecture/` | Архитектурные документы | ARCHITECTURE-RECON.md, ARCHITECTURE-AGENT-ROUTING.md и другие лежат в `docs/` root — должны быть тут |
| `docs/runbooks/` | Специфические runbooks | Нужны: safeguarding-recon.md, transaction-monitor.md, mcp-server.md |
| `docs/compliance/` | FCA control mapping | CASS 15 controls, AML controls, PS22/9 controls |

#### E3. Архитектурные docs в неправильном месте

Следующие файлы лежат в `docs/` root, а должны быть в `docs/architecture/`:
- `ARCHITECTURE-RECON.md`
- `ARCHITECTURE-AGENT-ROUTING.md`
- `ARCHITECTURE-16-AI-DESIGN-SYSTEM.md`
- `ARCHITECTURE-17-COMPLIANCE-AI-COPILOT.md`
- `ARCHITECTURE-AI-DESIGN-SYSTEM.md` ← вероятно дубликат
- `ARCHITECTURE-DESIGN-TO-CODE.md`

#### E4. Отсутствующие архитектурные документы

| Нужный документ | Для чего | IL |
|----------------|----------|-----|
| `docs/architecture/ARCHITECTURE-TRANSACTION-MONITOR.md` | Realtime TM Agent — scoring pipeline, alert routing, velocity tracking | IL-071 |
| `docs/architecture/ARCHITECTURE-SAFEGUARDING-ENGINE.md` | Safeguarding Engine CASS 15 — full microservice architecture | IL-SAF-01 |
| `docs/architecture/ARCHITECTURE-MCP-SERVER.md` | MCP server tools registry, auth, audit integration | IL-MCP-01 |
| `docs/architecture/ARCHITECTURE-COMPLIANCE-KB.md` | Compliance KB RAG pipeline | IL-069 (есть в banxe-architecture как ARCHITECTURE-18, не зеркалируется) |

---

## Сводная таблица приоритетов

| # | Gap | Критичность | Объём | IL |
|---|-----|------------|-------|-----|
| 1 | **IL-SAF-01 не в INSTRUCTION-LEDGER** (~40 commits, prod microservice) | **CRITICAL** | XL | IL-078 нужен |
| 2 | **IL-MCP-01 не в INSTRUCTION-LEDGER** (4 commits, published API) | HIGH | L | IL-074 нужен |
| 3 | **IL-ARL-01/D2C-01/ADDS-01 не в INSTRUCTION-LEDGER** | HIGH | M×3 | IL-075/076/077 |
| 4 | **IL-SK-01 не в INSTRUCTION-LEDGER** | HIGH | M | IL-073 |
| 5 | **IL-073..089 gap** (17 ILs не зарегистрированы) | HIGH | — | Batch registration |
| 6 | **docs/API.md устарел на 25+ ILs** | HIGH | XL | Docs update |
| 7 | **project_safeguarding.md отсутствует** в .claude/memory | MEDIUM | S | Create file |
| 8 | **50-frontend.md / 70-mcp-tools.md / 80-ai-agents.md** отсутствуют в .claude/rules | MEDIUM | M×3 | Create files |
| 9 | **ADR-002..ADR-009** отсутствуют | MEDIUM | S×8 | Create ADRs |
| 10 | **docs/runbooks/ и docs/compliance/** — только README | MEDIUM | M | Create docs |
| 11 | **IL-027 gap** в числовой последовательности | LOW | S | Document or mark |
| 12 | **docs/RUNBOOK.md + ONBOARDING.md** устарели (IL-017) | LOW | M | Update |
| 13 | **Arch docs в неправильном месте** (docs/ root vs docs/architecture/) | LOW | S | Reorganize |
| 14 | **project_mcp.md + project_sk.md** отсутствуют в .claude/memory | LOW | S×2 | Create files |

---

## Топ-3 немедленных действия (после READ-ONLY завершён)

1. **Зарегистрировать IL-SAF-01 как IL-078** в INSTRUCTION-LEDGER — ~40 коммитов без записи (самый большой gap)
2. **Зарегистрировать IL-073..077** (SK/MCP/ARL/D2C/ADDS) + IL-080..089 (arch docs) — нормализовать счётчик
3. **Обновить docs/API.md** — не обновлялся с IL-017 (25+ ILs назад)

---

## Хорошее состояние (без gaps)

- `.claude/rules/quality-gates.md` ✅ (обновлён сегодня)
- `.claude/memory/` для CKS/CEC/RTM/ADDS/ARL/D2C ✅ (все созданы)
- `banxe-architecture/INSTRUCTION-LEDGER.md` IL-006..IL-072 ✅ (все зарегистрированы, все DONE)
- `docs/adr/ADR-001-biome-vs-eslint.md` ✅ (создан сегодня)
- `.semgrep/banxe-rules.yml` ✅ (10 правил)
- Все pre-commit хуки ✅ (ruff + biome + semgrep + pytest)
- 1931 тест зелёный ✅

---

*Отчёт создан: 2026-04-12 | READ-ONLY — никакие файлы кроме этого не изменены*
