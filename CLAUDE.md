# CLAUDE.md — Banxe AI Bank: EMI Financial Analytics Stack
# FinDev Agent | P0 Execution Repo | Version: 1.0.0
# FCA CASS 15 / PS25/12 | Deadline: 7 May 2026

## ОБЯЗАТЕЛЬНО ПРОЧЕСТЬ ПЕРВЫМ

Это P0 execution repo для финансово-аналитического блока Banxe AI Bank.
**Scope:** только CASS 15 P0 items до 7 May 2026.
**НЕ scope:** AML, KYC, Cards, K8s, полный event streaming.

Главный архитектурный репо: https://github.com/CarmiBanxe/banxe-architecture
Instruction Ledger: banxe-architecture/INSTRUCTION-LEDGER.md
Compliance Matrix: banxe-architecture/docs/COMPLIANCE-MATRIX.md
Research base: banxe-architecture/docs/financial-analytics-research.md

---

## 0. FinDev Agent — Роль и ограничения

**Специализация:** FCA CASS 15 compliance engineering.

**Hard Constraints (НЕЛЬЗЯ):**
1. НИКОГДА float для денег — только `Decimal` (Python) / `Decimal(20,8)` (SQL)
2. НИКОГДА секреты в коде — только `.env` / переменные окружения
3. НИКОГДА технологии из санкционных юрисдикций (РФ, Иран, КНДР, Беларусь, Сирия)
4. ВСЕГДА audit trail — каждое финансовое действие логируется в ClickHouse / pgAudit
5. НИКОГДА платные SaaS без self-hosted альтернативы в production

**Приоритет задач:**
```
P0 (до 7 May 2026):
  1. pgAudit на всех PostgreSQL БД
  2. Daily safeguarding reconciliation (Blnk / bankstatementparser + Midaz)
  3. FIN060 generation → RegData
  4. Frankfurter FX rates (self-hosted ECB)
  5. adorsys PSD2 gateway (bank statement polling)

P1 (Q2-Q3 2026): Metabase/Superset, Great Expectations, Debezium, Temporal, Kafka
P2 (Q4 2026): Camunda 7, OpenMetadata, Airbyte
P3 (Year 2+): FinGPT, OpenBB, Apache Flink
```

---

## 1. P0 Stack Map

```
┌──────────────────────────────────────────────────────────────┐
│              BANXE EMI — P0 ANALYTICS STACK                  │
│              FCA CASS 15 | Deadline: 7 May 2026              │
├──────────────────┬───────────────────┬───────────────────────┤
│  LEDGER          │  RECONCILIATION   │  REPORTING            │
├──────────────────┼───────────────────┼───────────────────────┤
│ Midaz :8095      │ Blnk Finance      │ dbt Core              │
│ (PRIMARY CBS)    │ bankstatementparser│ (staging→marts→fin060)│
│ LedgerPort ABC   │ (CAMT.053/MT940)  │ JasperReports /       │
│ create_tx()      │ ReconciliationEng │ WeasyPrint            │
│ get_balance()    │ StatementFetcher  │ → FIN060 PDF          │
│                  │                   │ → RegData upload      │
├──────────────────┼───────────────────┼───────────────────────┤
│  AUDIT TRAIL     │  FX / RATES       │  INFRASTRUCTURE       │
├──────────────────┼───────────────────┼───────────────────────┤
│ pgAudit          │ Frankfurter       │ PostgreSQL 17 :5432   │
│ ClickHouse :9000 │ (self-hosted ECB) │ ClickHouse :9000      │
│ (5yr TTL append) │ 160+ currencies   │ Redis :6379           │
│ safeguarding_    │ No API key needed │ n8n :5678 (workflows) │
│ events table     │                   │                       │
└──────────────────┴───────────────────┴───────────────────────┘
                   adorsys PSD2 Gateway
                   → CAMT.053 bank statement auto-pull
```

---

## 2. Repo Structure (P0 scope only)

```
banxe-emi-stack/
├── CLAUDE.md                    ← этот файл
├── .env.example                 ← шаблон переменных окружения
├── .claude/
│   └── agents/
│       ├── reconciliation-agent.md   ← P0 daily recon agent
│       └── reporting-agent.md        ← P0 FIN060 reporting agent
├── docker/
│   ├── docker-compose.recon.yml      ← Blnk + bankstatementparser + pgAudit
│   └── docker-compose.reporting.yml  ← dbt + JasperReports/WeasyPrint
├── services/
│   ├── ledger/
│   │   └── midaz_client.py           ← async Midaz API client
│   ├── recon/
│   │   ├── reconciliation_engine.py  ← CASS 7.15 engine (mirrors vibe-coding)
│   │   ├── statement_fetcher.py      ← CSV + CAMT.053 statement reader
│   │   └── bankstatement_parser.py   ← CAMT.053/MT940 parser wrapper
│   └── reporting/
│       └── fin060_generator.py       ← FIN060a/b PDF generation
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml
│   └── models/
│       ├── staging/
│       │   └── stg_ledger_transactions.sql
│       └── marts/
│           ├── safeguarding/
│           │   └── safeguarding_daily.sql
│           └── fin060/
│               └── fin060_monthly.sql
└── scripts/
    ├── daily-recon.sh               ← P0 CASS 7.15 cron
    ├── monthly-fca-return.sh        ← FIN060 → RegData
    └── audit-export.sh              ← annual audit export
```

---

## 3. Связанные репозитории

| Репо | URL | Назначение |
|------|-----|-----------|
| banxe-architecture | github.com/CarmiBanxe/banxe-architecture | Архитектура, IL, ADR, COMPLIANCE-MATRIX |
| vibe-coding | github.com/CarmiBanxe/vibe-coding | Compliance engine, AML stack, Midaz adapter |
| **banxe-emi-stack** | github.com/CarmiBanxe/banxe-emi-stack | **P0 Financial Analytics (этот репо)** |

---

## 4. Ссылки на существующий код

ReconciliationEngine и StatementFetcher уже реализованы в vibe-coding:
```
vibe-coding/src/compliance/recon/reconciliation_engine.py  (commit 3f7060f)
vibe-coding/src/compliance/recon/statement_fetcher.py      (commit 3f7060f)
vibe-coding/src/compliance/recon/test_reconciliation.py    (T-16..T-30, 15/15)
```

Этот репо расширяет их:
- Добавляет CAMT.053 parser (bankstatementparser lib)
- Добавляет dbt трансформации для FIN060
- Добавляет PDF generation для RegData
- Добавляет pgAudit конфигурацию

---

## 5. Правила git workflow

- main branch protected — только через PR
- Каждый commit = один P0 item
- Commit message: `feat(P0-FA-NN): описание`
- IL update обязателен после каждого шага
