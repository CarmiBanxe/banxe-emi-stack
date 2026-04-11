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
