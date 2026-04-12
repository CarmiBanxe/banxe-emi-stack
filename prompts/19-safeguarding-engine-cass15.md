# Prompt 19 — Safeguarding Engine (CASS 15)

## Metadata
- **ID**: IL-SAF-01
- **Phase**: 3.6 — Safeguarding & Client Fund Protection
- **Priority**: P0 (Regulatory Blocker)
- **Deadline**: 7 May 2026
- **Roadmap Blocks**: J-engine, J-audit, E-safeguard
- **Dependencies**: D-gl (Midaz ledger), D-recon (reconciliation), compliance-service (IL-CKS-01)
- **Owner**: CEO + CTIO

## Context

Banxe is a UK FCA-authorised Electronic Money Institution (EMI). Under FCA PS10/15 and CASS 15 (Client Assets Sourcebook), ALL client e-money must be safeguarded in segregated accounts within ONE business day of receipt. Failure to comply risks FCA enforcement, licence suspension, and inability to hold client funds.

The ROADMAP-MATRIX identifies J-engine as "Zero implementation" and "the single largest regulatory risk." This prompt creates the complete Safeguarding Engine.

## Regulatory Requirements (FCA EMI Safeguarding)

### CASS 15 Core Rules
1. **Segregation**: Client funds MUST be held in designated safeguarding accounts, separate from firm funds
2. **Timeliness**: Funds must be safeguarded by end of NEXT business day after receipt
3. **Reconciliation**: Daily internal reconciliation + monthly external reconciliation
4. **Record-keeping**: Maintain accurate records sufficient to distinguish client funds at all times
5. **Acknowledgement letters**: Obtain from each safeguarding bank/custodian
6. **Breach reporting**: Notify FCA within 1 business day of any material breach

### PS10/15 Specific
- Relevant funds = all e-money float + fees not yet deducted
- Safeguarding methods: (a) segregated account, (b) insurance/guarantee, (c) investment in secure liquid assets
- Banxe uses method (a) — segregated bank accounts

## Infrastructure Checklist

```yaml
service_name: safeguarding-engine
port: 8094
stack:
  language: Python 3.11+
  framework: FastAPI
  orm: SQLAlchemy 2.0 + asyncpg
  database: PostgreSQL 15 (dedicated safeguarding schema)
  cache: Redis 7
  queue: Redis Streams / Celery
  audit_store: ClickHouse (immutable append-only)
  monitoring: Prometheus + Grafana
  ci: GitHub Actions (pytest + Semgrep + CodeQL)

docker:
  dockerfile: services/safeguarding-engine/Dockerfile
  compose_profile: safeguarding
  healthcheck: /health
  resources:
    memory: 512MB
    cpu: 0.5

testing:
  min_coverage: 90%
  frameworks: [pytest, pytest-asyncio, httpx]

## Directory Structure

```
services/safeguarding-engine/
├── Dockerfile
├── pyproject.toml
├── README.md
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 001_initial_safeguarding_schema.py
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory
│   ├── config.py                  # Settings via pydantic-settings
│   ├── dependencies.py            # DI: db session, redis, clickhouse
│   ├── api/
│   │   ├── __init__.py
│   │   ├── router.py              # Main API router
│   │   ├── safeguarding.py        # POST /safeguard, GET /positions
│   │   ├── reconciliation.py      # POST /reconcile, GET /reconcile/history
│   │   ├── accounts.py            # CRUD safeguarding accounts
│   │   ├── breach.py              # POST /breach/report, GET /breaches
│   │   └── health.py              # GET /health, /ready
│   ├── models/
│   │   ├── __init__.py
│   │   ├── safeguarding_account.py
│   │   ├── safeguarding_position.py
│   │   ├── reconciliation_record.py
│   │   ├── breach_report.py
│   │   └── audit_event.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── safeguarding.py
│   │   ├── reconciliation.py
│   │   ├── breach.py
│   │   └── common.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── safeguarding_service.py     # Core safeguarding logic
│   │   ├── reconciliation_service.py   # Daily + monthly recon
│   │   ├── breach_service.py           # Breach detection + FCA notify
│   │   ├── position_calculator.py      # Calculate safeguarding requirements
│   │   ├── audit_logger.py             # ClickHouse immutable audit
│   │   └── scheduler.py               # Celery beat: daily recon, position calc
│   ├── integrations/
│   │   ├── __init__.py
│   │   ├── midaz_client.py             # Midaz GL ledger balances
│   │   ├── bank_api_client.py          # Safeguarding bank account balances
│   │   ├── compliance_client.py        # compliance-service (IL-CKS-01)
│   │   └── notification_client.py      # Telegram + email alerts
│   └── mcp/
│       ├── __init__.py
│       ├── server.py                   # MCP tool server
│       └── tools/
│           ├── safeguarding_position.py
│           ├── reconciliation_status.py
│           ├── breach_report.py
│           └── safeguarding_health.py
└── tests/
    ├── conftest.py
    ├── test_safeguarding_service.py
    ├── test_reconciliation_service.py
    ├── test_breach_service.py
    ├── test_position_calculator.py
    ├── test_audit_logger.py
    ├── test_api_safeguarding.py
    ├── test_api_reconciliation.py
    ├── test_api_breach.py

    ## API Endpoints

### Safeguarding Core
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/safeguard` | Record new safeguarding obligation (triggered on e-money receipt) |
| GET | `/api/v1/positions` | Current safeguarding position summary |
| GET | `/api/v1/positions/{date}` | Historical position for specific date |
| GET | `/api/v1/positions/shortfall` | Calculate any shortfall vs required |

### Safeguarding Accounts
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/accounts` | Register a safeguarding bank account |
| GET | `/api/v1/accounts` | List all safeguarding accounts |
| GET | `/api/v1/accounts/{id}` | Account details + balance history |
| PUT | `/api/v1/accounts/{id}` | Update account metadata |
| POST | `/api/v1/accounts/{id}/balance` | Record balance snapshot from bank |

### Reconciliation
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/reconcile/daily` | Trigger daily internal reconciliation |
| POST | `/api/v1/reconcile/monthly` | Trigger monthly external reconciliation |
| GET | `/api/v1/reconcile/history` | List reconciliation results |
| GET | `/api/v1/reconcile/{id}` | Detailed reconciliation report |

### Breach Management
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/breaches` | Report a safeguarding breach |
| GET | `/api/v1/breaches` | List all breaches (with filters) |
| GET | `/api/v1/breaches/{id}` | Breach detail + remediation timeline |
| PUT | `/api/v1/breaches/{id}/resolve` | Mark breach as resolved |

### Audit Trail
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/audit/events` | Query immutable audit log (ClickHouse) |
| GET | `/api/v1/audit/report` | Generate FCA-producible audit report |
    └── test_mcp_tools.py
```

## Database Schema (PostgreSQL)

```sql
CREATE SCHEMA safeguarding;

-- Safeguarding bank accounts (segregated)
CREATE TABLE safeguarding.accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bank_name VARCHAR(255) NOT NULL,
    account_number VARCHAR(50) NOT NULL,
    sort_code VARCHAR(10),
    iban VARCHAR(34),
    currency VARCHAR(3) NOT NULL DEFAULT 'GBP',
    account_type VARCHAR(20) NOT NULL DEFAULT 'segregated',
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    acknowledgement_letter_received BOOLEAN DEFAULT FALSE,
    acknowledgement_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Daily safeguarding positions
CREATE TABLE safeguarding.positions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_date DATE NOT NULL,
    total_client_funds DECIMAL(18,2) NOT NULL,
    total_safeguarded DECIMAL(18,2) NOT NULL,
    shortfall DECIMAL(18,2) GENERATED ALWAYS AS (total_client_funds - total_safeguarded) STORED,
    is_compliant BOOLEAN GENERATED ALWAYS AS (total_safeguarded >= total_client_funds) STORED,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(position_date)
);

-- Position breakdown by account
CREATE TABLE safeguarding.position_details (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    position_id UUID NOT NULL REFERENCES safeguarding.positions(id),
    account_id UUID NOT NULL REFERENCES safeguarding.accounts(id),
    balance DECIMAL(18,2) NOT NULL,
    balance_source VARCHAR(20) NOT NULL, -- 'bank_api', 'manual', 'statement'
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Reconciliation records
CREATE TABLE safeguarding.reconciliations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recon_type VARCHAR(10) NOT NULL, -- 'daily', 'monthly'
    recon_date DATE NOT NULL,
    ledger_total DECIMAL(18,2) NOT NULL,
    bank_total DECIMAL(18,2) NOT NULL,
    difference DECIMAL(18,2) GENERATED ALWAYS AS (ledger_total - bank_total) STORED,
    status VARCHAR(20) NOT NULL, -- 'matched', 'break', 'pending'
    break_items JSONB DEFAULT '[]',
    resolved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Breach reports
CREATE TABLE safeguarding.breaches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    breach_type VARCHAR(50) NOT NULL,
    severity VARCHAR(10) NOT NULL, -- 'critical', 'major', 'minor'
    description TEXT NOT NULL,
    shortfall_amount DECIMAL(18,2),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    fca_notified BOOLEAN DEFAULT FALSE,
    fca_notified_at TIMESTAMPTZ,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_at TIMESTAMPTZ,
    remediation_notes TEXT,
    created_by VARCHAR(100) NOT NULL DEFAULT 'system'
);

## ClickHouse Audit Schema (Immutable)

```sql
CREATE TABLE safeguarding_audit (
    event_id UUID,
    event_type String,
    entity_type String,
    entity_id UUID,
    action String,
    actor String,
    details String,
    position_date Date,
    amount Decimal(18,2),
    timestamp DateTime64(3, 'UTC'),
    ttl_expiry Date DEFAULT toDate(timestamp) + INTERVAL 7 YEAR
) ENGINE = MergeTree()
ORDER BY (event_type, timestamp)
TTL ttl_expiry;
```

## MCP Tools (4 tools)

### 1. `safeguarding_position`
- **Description**: Get current safeguarding position, shortfall, compliance status
- **Input**: `{date?: string}` (defaults to today)
- **Output**: `{total_client_funds, total_safeguarded, shortfall, is_compliant, accounts[]}`

### 2. `reconciliation_status`
- **Description**: Get latest reconciliation results
- **Input**: `{type?: 'daily'|'monthly', limit?: number}`
- **Output**: `{reconciliations[], last_matched, breaks_count}`

### 3. `breach_report`
- **Description**: List active breaches or report new breach
- **Input**: `{action: 'list'|'report', breach_type?, description?}`
- **Output**: `{breaches[], total_active, fca_notifications_pending}`

### 4. `safeguarding_health`
- **Description**: Overall safeguarding health dashboard
- **Input**: `{}`
- **Output**: `{position_compliant, last_recon_date, active_breaches, accounts_count, acknowledgement_status}`

- ## Business Logic Rules

### Position Calculation
1. Query Midaz GL for total client e-money liabilities
2. Query each safeguarding bank account for current balance
3. Calculate: `shortfall = client_funds - safeguarded_total`
4. If `shortfall > 0`: trigger CRITICAL breach alert
5. Store position in PostgreSQL + audit event in ClickHouse
6. Run daily via Celery beat at 06:00 UTC

### Daily Reconciliation
1. Compare Midaz ledger client fund total vs safeguarding account balances
2. Tolerance: GBP 0.01 (penny-exact matching required)
3. Any difference > tolerance = reconciliation break
4. Breaks auto-escalate: Telegram alert to MLRO + CEO
5. Unresolved breaks after 24h trigger FCA breach report

### Monthly External Reconciliation
1. Match bank statements (imported/API) against internal records
2. Produce FCA-producible reconciliation report
3. Flag unmatched items for manual review
4. Store complete audit trail in ClickHouse (7-year TTL)

### Breach Detection & FCA Notification
- **Auto-detect**: shortfall, late safeguarding (>T+1), recon break >24h
- **Severity levels**: critical (shortfall), major (timing breach), minor (recon break <tolerance)
- **FCA notification**: within 1 business day for critical/major breaches
- **Notification chain**: Telegram -> Email -> n8n workflow -> FCA Gabriel upload

## Integration Points

| Service | Direction | Purpose |
|---------|-----------|--------|
| Midaz GL (D-gl) | Inbound | Client fund liabilities, ledger balances |
| compliance-service (IL-CKS-01) | Outbound | Regulatory event logging |
| Bank API | Inbound | Safeguarding account balance feeds |
| ClickHouse | Outbound | Immutable audit trail (7Y retention) |
| Telegram Bot | Outbound | Real-time breach alerts |
| n8n | Outbound | FCA Gabriel submission workflow |
| Redis | Internal | Caching, task queue, rate limiting |

## Execution Instructions

```bash
# Run from repo root on Legion machine
cd /home/user/banxe-emi-stack

# Create service scaffold
mkdir -p services/safeguarding-engine/app/{api,models,schemas,services,integrations,mcp/tools}
mkdir -p services/safeguarding-engine/{tests,alembic/versions}

# Implementation order:
# 1. config.py + main.py (FastAPI factory)
# 2. models/ (SQLAlchemy ORM)
# 3. schemas/ (Pydantic v2)
# 4. services/safeguarding_service.py (core logic)
# 5. services/position_calculator.py
# 6. services/reconciliation_service.py
# 7. services/breach_service.py
# 8. services/audit_logger.py (ClickHouse)
# 9. services/scheduler.py (Celery beat)
# 10. api/ endpoints
# 11. integrations/ (Midaz, bank, compliance, telegram)
# 12. mcp/ tools
# 13. tests/ (90%+ coverage target)
# 14. Dockerfile + docker-compose update
# 15. alembic migration
```

## Acceptance Criteria

- [ ] All 16 API endpoints functional
- [ ] PostgreSQL schema with 5 tables created via Alembic
- [ ] ClickHouse audit table with 7-year TTL
- [ ] Daily position calculation via Celery beat
- [ ] Daily + monthly reconciliation engine
- [ ] Breach auto-detection with severity classification
- [ ] FCA notification chain (Telegram -> Email -> n8n)
- [ ] 4 MCP tools registered and functional
- [ ] 90%+ test coverage (pytest)
- [ ] Docker container builds and passes healthcheck
- [ ] Integration with Midaz GL client
- [ ] Immutable audit trail for all safeguarding events
- [ ] README.md with setup and operational guide
```
  fixtures: conftest.py with async DB + Redis
```
