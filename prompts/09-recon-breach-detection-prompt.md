# 09 — Reconciliation & Breach Detection — Claude Code Prompt

## Created: 2026-04-11 | IL-015 | Migration Phase: 4
## Updated: 2026-04-11 | IL-015 | Phases 2-5 implemented ✅

## Context

You are working on **banxe-emi-stack**, an open-source EMI (Electronic Money Institution) analytics platform regulated by FCA.

**Regulatory basis:**
- **FCA CASS 7.15** — daily internal vs external reconciliation of safeguarding accounts
- **FCA CASS 15.12 / PS25/12** — if a safeguarding discrepancy persists ≥ 3 business days, the firm MUST notify FCA via RegData within 1 business day, escalate to CEO + CTIO

## Architecture Principles (CANON)

1. **Protocol-based DI** — all external dependencies injected via `typing.Protocol` (LedgerPortProtocol, ClickHouseClientProtocol, BreachClientProtocol, StatementFetcherProtocol)
2. **Decimal-only** — NEVER use `float` for monetary values (FCA I-24). All amounts are `Decimal`, passed as `str` to ClickHouse
3. **CTX-06 AMBER** — ReconciliationEngine calls LedgerPort only, never Midaz HTTP directly
4. **Threshold CEO decision** — £1.00 discrepancy tolerance (D-RECON-DESIGN.md Q3)
5. **InMemory test stubs** — every Protocol has an in-memory implementation for unit tests

## Module Map

| Module | Purpose | Phase |
|--------|---------|-------|
| `services.recon.reconciliation_engine` | ReconciliationEngine — daily CASS 7.15 recon | 1 ✅ |
| `services.recon.breach_detector` | BreachDetector — CASS 15.12 breach escalation | 1 ✅ |
| `services.recon.clickhouse_client` | ClickHouseReconClient + InMemoryReconClient | 1 ✅ |
| `services.recon.statement_fetcher` | StatementFetcher — bank statement polling | 1+2 ✅ |
| `services.recon.bankstatement_parser` | CSV/MT940/CAMT.053 parser + validate_statement_balance | 1+2 ✅ |
| `services.recon.statement_poller` | Sync + async polling (async_poll_with_schedule) | 1+2 ✅ |
| `services.recon.fca_regdata_client` | FCARegDataClient + MockFCARegDataClient | 4 ✅ |
| `services.recon.cron_daily_recon` | Cron entry point for daily reconciliation | 1 ✅ |
| `services.recon.midaz_reconciliation` | CLI entry point (`python3 -m`) | 1 ✅ |
| `services.recon.mock_aspsp` | Mock bank API for sandbox testing | 1 ✅ |
| `agents.compliance.skills.recon_analysis` | ReconAnalysisSkill — AI discrepancy classification | 5 ✅ |
| `agents.compliance.skills.breach_prediction` | BreachPredictionSkill — trend-based prediction | 5 ✅ |
| `agents.compliance.workflows.daily_recon_workflow` | Orchestrated daily workflow (all 4 steps) | 5 ✅ |
| `infra/clickhouse/migrations/` | Production ClickHouse schema migrations | 3 ✅ |
| `infra/grafana/dashboards/` | Grafana safeguarding dashboard | 3 ✅ |
| `n8n/workflows/safeguarding-shortfall-alert.json` | Enhanced alert workflow | 4 ✅ |
| `n8n/workflows/daily-recon-report.json` | Daily 18:00 UTC report → #daily-recon | 4 ✅ |

## Data Flow

```
Bank / ASPSP (CSV / MT940)
        │
        ▼
  StatementFetcher
        │
        ▼
ReconciliationEngine  ◀──── LedgerPort (Midaz CBS via Protocol DI)
  (CASS 7.15)
        │
        ▼
  ClickHouseReconClient
  (safeguarding_events)
        │
        ▼
  BreachDetector (CASS 15.12)
  streak ≥ 3 business days?
        │ YES
        ▼
  n8n Webhook
  → Slack alert
  → FCA RegData notification
  → CEO + CTIO escalation
```
