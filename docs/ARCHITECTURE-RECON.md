# Architecture: Block D — Reconciliation & Breach Detection

**Version:** 0.1.0 | **Updated:** 2026-04-11 | IL-015
**FCA Rules:** CASS 7.15 (daily recon), CASS 15.12 / PS25/12 (breach notification)

## Overview

Block D implements daily safeguarding reconciliation — comparing internal ledger balances (Midaz CBS via LedgerPort) against external bank statements (ASPSP). Discrepancies persisting ≥ 3 business days trigger FCA breach notification.

## Component Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Bank / ASPSP   │────▶│ StatementFetcher  │────▶│                 │
│ (CSV / MT940)   │     │                  │     │  Reconciliation  │
└─────────────────┘     └──────────────────┘     │    Engine        │
                                                  │                  │
┌─────────────────┐                               │  (CASS 7.15)    │
│   Midaz CBS     │────▶  LedgerPort  ───────────▶│                 │
│  (via Port)     │       (Protocol DI)            └────────┬────────┘
└─────────────────┘                                         │
                                                            ▼
                                                  ┌─────────────────┐
                                                  │   ClickHouse    │
                                                  │  safeguarding   │
                                                  │    _events      │
                                                  └────────┬────────┘
                                                           │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │ BreachDetector  │
                                                  │  (CASS 15.12)   │
                                                  │  streak ≥ 3d?   │
                                                  └────────┬────────┘
                                                           │ YES
                                                           ▼
                                                  ┌──────────────────────┐
                                                  │    n8n Webhook       │
                                                  │  → Slack alert       │
                                                  │  → FCA RegData       │
                                                  │  → CEO/CTIO escalate │
                                                  └──────────────────────┘
```

## ClickHouse Schema

### `banxe.safeguarding_events`

| Column | Type | Description |
|--------|------|-------------|
| recon_date | Date | Reconciliation date |
| account_id | String | Midaz account UUID |
| account_type | String | `operational` / `client_funds` |
| currency | String | ISO-4217 |
| internal_balance | Decimal(18,2) | Midaz CBS balance |
| external_balance | Decimal(18,2) | Bank statement balance |
| discrepancy | Decimal(18,2) | external - internal |
| status | String | MATCHED / DISCREPANCY / PENDING |
| alert_sent | UInt8 | 1 if n8n alert fired |
| source_file | String | Statement filename |

### `banxe.safeguarding_breaches`

| Column | Type | Description |
|--------|------|-------------|
| account_id | String | Midaz account UUID |
| account_type | String | `operational` / `client_funds` |
| currency | String | ISO-4217 |
| discrepancy | Decimal(18,2) | Absolute discrepancy |
| days_outstanding | UInt32 | Consecutive DISCREPANCY days |
| first_seen | Date | Streak start date |
| latest_date | Date | Most recent DISCREPANCY date |

## Safeguarding Accounts (ADR-013 Block J Phase 1)

| Account ID | Type |
|------------|------|
| `019d6332-f274-709a-b3a7-983bc8745886` | operational (asset) |
| `019d6332-da7f-752f-b9fd-fa1c6fc777ec` | client_funds (liability) |

**Org ID:** `019d6301-32d7-70a1-bc77-0a05379ee510`
**Ledger ID:** `019d632f-519e-7865-8a30-3c33991bba9c`

## Design Decisions

- **Threshold £1.00** — CEO decision (D-RECON-DESIGN.md Q3). Differences ≤ £1 classified as MATCHED.
- **Breach amount £10** — minimum reportable discrepancy (configurable via `BREACH_AMOUNT_GBP`)
- **Never float** — all monetary values `Decimal`, passed as `str` to ClickHouse driver (FCA I-24)
- **Protocol DI** — enables InMemory stubs for unit tests without ClickHouse/Midaz

---

## Phase 2: Enhanced ASPSP Integration + Parsers

**Implemented:** 2026-04-11 | IL-015

### New capabilities
- `StatementFetcher.fetch_with_oauth()` — OAuth2 flow for real ASPSP API with 3-attempt exponential backoff (1s, 2s, 4s)
- `validate_statement_balance()` — FCA integrity check: sum(transactions) == closing - opening
- `async_poll_with_schedule()` — asyncio polling at 06:00/09:00/12:00 UTC windows, then PENDING

### Environment variables (Phase 2)
| Var | Purpose |
|-----|---------|
| `ASPSP_BASE_URL` | ASPSP API base URL |
| `ASPSP_CLIENT_ID` | OAuth2 client ID |
| `ASPSP_CLIENT_SECRET` | OAuth2 client secret |
| `ASPSP_CERT_PATH` | mTLS certificate path (eIDAS) |

---

## Phase 3: ClickHouse Production Schema + Grafana

**Implemented:** 2026-04-11 | IL-015

### Migrations (infra/clickhouse/migrations/)
| File | Object | Purpose |
|------|--------|---------|
| `001_create_safeguarding_events.sql` | `banxe.safeguarding_events` | Daily recon audit (5yr TTL) |
| `002_create_safeguarding_breaches.sql` | `banxe.safeguarding_breaches` | Breach records (5yr TTL) |
| `003_create_recon_summary_mv.sql` | `banxe.recon_daily_summary` | Materialized view for dashboard |
| `004_create_fca_notifications.sql` | `banxe.fca_notifications` | FCA RegData submissions (5yr TTL) |

### New API: `get_recon_summary(date_from, date_to) → list[dict]`
Both `ClickHouseReconClient` and `InMemoryReconClient` implement this method.
Returns recon status summary grouped by date and status for dashboard API.

### Grafana dashboard
- File: `infra/grafana/dashboards/safeguarding-recon.json`
- 5 panels: status stacked bar, discrepancy trend, active breaches table, days-since-matched stat, breach history timeline
- Datasource: `grafana-clickhouse-datasource`

---

## Phase 4: FCA RegData Auto-Submission + n8n Workflows

**Implemented:** 2026-04-11 | IL-015

### FCARegDataClient
- **Production:** `FCARegDataClient` — submits to `FCA_REGDATA_URL/api/v1/notifications/safeguarding-breach`
- **Sandbox:** `MockFCARegDataClient` — records notifications in-memory, returns mock FCA references
- `NotificationResult` — frozen dataclass: `success`, `fca_reference`, `submitted_at`, `error`

### n8n Workflows
| Workflow | File | Trigger |
|----------|------|---------|
| Safeguarding Shortfall Alert | `safeguarding-shortfall-alert.json` | Webhook POST from BreachDetector |
| Daily Recon Report | `daily-recon-report.json` | Cron 18:00 UTC → Slack #daily-recon |

The enhanced shortfall alert includes: Slack #compliance-alerts, Email CEO+CTIO, FCA RegData POST, ClickHouse audit log, Telegram bot (if token set).

---

## Phase 5: AI Agent Integration

**Implemented:** 2026-04-11 | IL-015

### Architecture Extension

```
┌─────────────────┐
│ ReconciliationEngine │
│  → List[ReconResult] │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐     ┌──────────────────────────┐
│  ReconAnalysisSkill  │────▶│   AnalysisReport          │
│  (rule-based, Ph0)  │     │  classification, confidence│
│  FRAUD_RISK if >50k │     │  HITL if confidence < 0.70│
│  SYSTEMATIC if 2+d  │     └──────────────────────────┘
└─────────────────────┘
         │
         ▼
┌──────────────────────┐     ┌──────────────────────────┐
│ BreachPredictionSkill │────▶│   PredictionResult        │
│  (moving avg + trend) │     │  probability, trend       │
│  IMPROVING / STABLE  │     │  predicted_breach_in_days │
│  DETERIORATING        │     └──────────────────────────┘
└──────────────────────┘
```

### Agent Soul files
| Agent | Soul | Autonomy | HITL Gate |
|-------|------|----------|-----------|
| recon-analysis-agent | `soul/recon_analysis_agent.soul.md` | L2 | confidence < 0.70, FRAUD_RISK |
| breach-prediction-agent | `soul/breach_prediction_agent.soul.md` | L2 | probability > 0.90, days <= 1 |

### Daily Workflow
`agents/compliance/workflows/daily_recon_workflow.py` — orchestrates all 4 steps:
1. ReconciliationEngine.reconcile()
2. BreachDetector.check_and_escalate()
3. ReconAnalysisSkill.analyze()
4. BreachPredictionSkill.predict() per DISCREPANCY account
