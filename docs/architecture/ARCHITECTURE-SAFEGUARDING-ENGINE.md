# Architecture: Safeguarding Engine (CASS 15)

**IL:** IL-SAF-01 (IL-078) | **Created:** 2026-04-12
**FCA rules:** FCA CASS 15, PS25/12, CASS 15.12.4R

---

## Overview

Standalone FastAPI microservice for FCA CASS 15 compliance — tracking, reconciling, and reporting on client fund safeguarding positions.

## Component Map

```
PostgreSQL (safeguarding_accounts, positions, reconciliations, breaches)
        ↓  SQLAlchemy async + Alembic migrations
SafeguardingService → account management, position queries
ReconciliationService → daily: Midaz balance ↔ bank statement
BreachService → DISCREPANCY > 3 days → FCA notification
PositionCalculator → daily position snapshots
AuditLogger → ClickHouse append-only (I-24)
        ↓
FastAPI (8 endpoints) + MCP tools (4)
```

## Services

| Service | Responsibility |
|---------|---------------|
| `SafeguardingService` | Account CRUD, position queries, CASS 15 compliance state |
| `ReconciliationService` | Daily sверка: internal balance (Midaz) ↔ external (CAMT.053) |
| `BreachService` | Detects DISCREPANCY persisting > `BREACH_DAYS` (default: 3) → writes to `safeguarding_breaches` |
| `PositionCalculator` | Aggregates daily balances per account and currency |
| `AuditLogger` | Appends every financial event to ClickHouse `banxe.safeguarding_events` (5yr TTL, I-08) |

## Database Schema (PostgreSQL)

| Table | Purpose |
|-------|---------|
| `safeguarding_accounts` | Account registry (id, account_type, iban, currency, status) |
| `safeguarding_positions` | Daily balance snapshots |
| `position_details` | Per-account breakdown |
| `reconciliation_records` | Recon results (MATCHED/DISCREPANCY/PENDING) |
| `safeguarding_breaches` | FCA breach notifications |

## Integrations

| Integration | Purpose | Port |
|-------------|---------|------|
| `MidazClient` | Get internal ledger balances | `LedgerPortProtocol` |
| `BankApiClient` | CAMT.053 / MT940 statement fetch | `StatementFetcherProtocol` |
| `ComplianceClient` | RegData FCA notifications | `RegDataPortProtocol` |
| `NotificationClient` | Slack/email alerts | `NotificationPortProtocol` |

## API Endpoints (8)

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

## MCP Tools (4)

`safeguarding_position`, `reconciliation_status`, `breach_report`, `safeguarding_health`

## Key Invariants

- **I-01:** All amounts are `Decimal` — never float
- **I-24:** `AuditLogger` → ClickHouse append-only (`banxe.safeguarding_events`, TTL 5yr)
- **CASS 15.2.2R:** Client funds always in segregated accounts (account_type = "client_funds")
- **CASS 15.12.4R:** Breach notification within 1 business day if DISCREPANCY persists ≥ 3 days

## Files

```
services/safeguarding-engine/
├── app/
│   ├── main.py, config.py, dependencies.py
│   ├── models/      — SQLAlchemy (5 tables)
│   ├── schemas/     — Pydantic (safeguarding, reconciliation, breach)
│   ├── services/    — SafeguardingService, ReconciliationService, BreachService, ...
│   ├── api/         — 5 routers
│   ├── mcp/         — 4 MCP tools
│   └── integrations/ — MidazClient, BankApiClient, ComplianceClient, NotificationClient
├── alembic/
├── Dockerfile
└── pyproject.toml
docker/docker-compose.recon.yml — includes safeguarding-engine
```
