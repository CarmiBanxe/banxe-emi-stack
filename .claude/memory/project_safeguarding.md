---
name: Project: Safeguarding Engine (IL-SAF-01)
description: Safeguarding Engine CASS 15 full microservice — FastAPI + SQLAlchemy + Alembic + MCP tools, prompt 19
type: project
---

# IL-SAF-01 — Safeguarding Engine (CASS 15)

**Status:** DONE ✅ (множество коммитов, ~40 total)
**Промпт:** 19-safeguarding-engine-cass15.md
**Репо:** banxe-emi-stack, branch: refactor/claude-ai-scaffold

## Что построено

Полноценный FastAPI микросервис для FCA CASS 15 compliance, вынесенный в отдельный модуль `services/safeguarding-engine/`.

### Структура
```
services/safeguarding-engine/
├── app/
│   ├── main.py           — FastAPI factory
│   ├── config.py         — pydantic-settings (env vars)
│   ├── dependencies.py   — DB, Redis, ClickHouse DI
│   ├── models/           — SQLAlchemy: accounts, positions, position_details, reconciliations, breaches
│   ├── schemas/          — Pydantic: safeguarding, reconciliation, breach, common
│   ├── services/         — SafeguardingService, ReconciliationService, BreachService, PositionCalculator, AuditLogger
│   ├── api/              — routers: safeguarding, reconciliation, breach, accounts, health
│   ├── mcp/              — MCP tools: safeguarding_position, reconciliation_status, breach_report, health
│   └── integrations/     — MidazClient, BankApiClient, ComplianceClient, NotificationClient
├── alembic/              — Alembic migrations (PostgreSQL)
├── Dockerfile
└── pyproject.toml
```

### Ключевые сервисы
- `SafeguardingService` — управление счетами CASS 15, позиции клиентских средств
- `ReconciliationService` — ежедневная сверка: Midaz balance ↔ bank statement
- `BreachService` — детекция нарушений (>3 дней discrepancy → FCA уведомление)
- `PositionCalculator` — расчёт daily position по всем счетам
- `AuditLogger` — append-only ClickHouse logging (I-24)

### API Endpoints (8)
```
GET  /health
GET  /v1/safeguarding/accounts
GET  /v1/safeguarding/position
POST /v1/safeguarding/accounts
GET  /v1/reconciliation/status
POST /v1/reconciliation/run
GET  /v1/breaches
POST /v1/breaches/report
```

### MCP Tools
- `safeguarding_position` — текущая позиция клиентских средств
- `reconciliation_status` — статус последней сверки
- `breach_report` — отчёт о нарушениях
- `safeguarding_health` — health dashboard

## Технологии
- FastAPI + Pydantic v2
- SQLAlchemy async (PostgreSQL)
- Alembic migrations
- Redis (distributed locks)
- ClickHouse (audit trail I-24)
- InMemory stubs для всех портов

## Инварианты
- I-01: Decimal для всех GBP сумм
- I-24: append-only ClickHouse audit
- CASS 15.2.2R: сегрегация клиентских средств

## Ключевые коммиты
- `28c35cd` — Add prompt 19 - Safeguarding Engine
- `84533b9` — app/config.py
- `7b8a944` — app/main.py
- `f638d89` — models/ (5 tables)
- Далее ~35 коммитов по `feat(safeguarding):` и `IL-SAF-01:`

## **Why:** CASS 15 P0 deadline 7 May 2026 — без Safeguarding Engine нельзя получить EMI лицензию.
## **How to apply:** При вопросах о позиции клиентских средств, сверке, или нарушениях — смотри `services/safeguarding-engine/`.
