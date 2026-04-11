# ClickHouse Migrations — BANXE safeguarding schema

## Overview

These SQL migrations create the ClickHouse schema for FCA CASS 7.15/15.12 reconciliation audit trail.

All tables use MergeTree engine with 5-year TTL (FCA I-08 invariant).

## Migrations

| File | Table | Purpose |
|------|-------|---------|
| `001_create_safeguarding_events.sql` | `banxe.safeguarding_events` | Daily recon audit trail |
| `002_create_safeguarding_breaches.sql` | `banxe.safeguarding_breaches` | FCA CASS 15.12 breach records |
| `003_create_recon_summary_mv.sql` | `banxe.recon_daily_summary` | Daily summary materialized view |
| `004_create_fca_notifications.sql` | `banxe.fca_notifications` | FCA RegData submission audit |

## How to Apply

### Via clickhouse-client CLI

```bash
# Apply in order (idempotent — CREATE IF NOT EXISTS)
clickhouse-client --host=localhost --port=9000 \
  --user=default --password="${CLICKHOUSE_PASSWORD}" \
  --query="$(cat 001_create_safeguarding_events.sql)"

clickhouse-client --host=localhost --port=9000 \
  --user=default --password="${CLICKHOUSE_PASSWORD}" \
  --query="$(cat 002_create_safeguarding_breaches.sql)"

clickhouse-client --host=localhost --port=9000 \
  --user=default --password="${CLICKHOUSE_PASSWORD}" \
  --query="$(cat 003_create_recon_summary_mv.sql)"

clickhouse-client --host=localhost --port=9000 \
  --user=default --password="${CLICKHOUSE_PASSWORD}" \
  --query="$(cat 004_create_fca_notifications.sql)"
```

### Via Python (ReconciliationEngine startup)

```python
from services.recon.clickhouse_client import ClickHouseReconClient
ch = ClickHouseReconClient()
ch.ensure_schema()
```

### Via Docker Compose init

Mount the migrations directory and run on startup:

```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24
    volumes:
      - ./infra/clickhouse/migrations:/docker-entrypoint-initdb.d
```

## FCA Requirements

- `safeguarding_events`: CASS 7.15 — daily reconciliation, 5yr retention
- `safeguarding_breaches`: CASS 15.12 — breach detection, 5yr retention
- `fca_notifications`: CASS 15.12 — RegData submissions, 5yr retention
- All amounts stored as `Decimal(18, 2)` — never float (I-24)
- TTL minimum 5 years (I-08) — do NOT reduce
