---
paths: ["services/**", "dbt/**", "docker/**"]
---

# CASS 15 Stack Map — BANXE EMI STACK

## P0 Stack Map

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

## Repo Structure (P0 scope)

```
banxe-emi-stack/
├── CLAUDE.md
├── .env.example
├── .claude/
│   ├── agents/
│   │   ├── reconciliation-agent.md
│   │   └── reporting-agent.md
│   ├── rules/          ← governance rules (this directory)
│   └── commands/       ← slash commands
├── docker/
│   ├── docker-compose.recon.yml
│   └── docker-compose.reporting.yml
├── services/
│   ├── ledger/midaz_client.py
│   ├── recon/
│   │   ├── reconciliation_engine.py
│   │   ├── statement_fetcher.py
│   │   └── bankstatement_parser.py
│   └── reporting/fin060_generator.py
├── dbt/
│   └── models/
│       ├── staging/stg_ledger_transactions.sql
│       └── marts/
│           ├── safeguarding/safeguarding_daily.sql
│           └── fin060/fin060_monthly.sql
└── scripts/
    ├── daily-recon.sh
    ├── monthly-fca-return.sh
    └── audit-export.sh
```

## Related Repos

| Repo | Purpose |
|------|---------|
| banxe-architecture | Architecture, IL, ADR, COMPLIANCE-MATRIX |
| vibe-coding | Compliance engine, AML stack, Midaz adapter |
| **banxe-emi-stack** | **P0 Financial Analytics (this repo)** |

## Existing Code (vibe-coding commit 3f7060f)

```
vibe-coding/src/compliance/recon/reconciliation_engine.py
vibe-coding/src/compliance/recon/statement_fetcher.py
vibe-coding/src/compliance/recon/test_reconciliation.py  (T-16..T-30, 15/15)
```
