# Safeguarding Engine (CASS 15)

> Banxe EMI Stack - FCA-compliant safeguarding engine for client fund protection

## Overview

The Safeguarding Engine implements FCA CASS 15 and PS10/15 requirements for Electronic Money Institution (EMI) client fund protection. It ensures all client e-money is safeguarded in segregated accounts within one business day of receipt.

## Key Features

- **Position Calculation**: Daily safeguarding position tracking with shortfall detection
- **Reconciliation**: Daily internal + monthly external reconciliation engine
- **Breach Management**: Auto-detection, severity classification, FCA notification chain
- **Audit Trail**: Immutable ClickHouse-based audit log with 7-year TTL
- **MCP Tools**: 4 AI-accessible tools for safeguarding monitoring

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| Framework | FastAPI |
| ORM | SQLAlchemy 2.0 + asyncpg |
| Database | PostgreSQL 15 |
| Cache/Queue | Redis 7 |
| Audit Store | ClickHouse |
| Monitoring | Prometheus + Grafana |

## Quick Start

```bash
# Build
docker build -t safeguarding-engine .

# Run
docker run -p 8094:8094 safeguarding-engine

# Run migrations
alembic upgrade head

# Run tests
pytest --cov=app --cov-report=term-missing
```

## API Endpoints

- `POST /api/v1/safeguard` - Record safeguarding obligation
- `GET /api/v1/positions` - Current position summary
- `GET /api/v1/positions/shortfall` - Calculate shortfall
- `POST /api/v1/reconcile/daily` - Trigger daily reconciliation
- `POST /api/v1/reconcile/monthly` - Trigger monthly reconciliation
- `POST /api/v1/breaches` - Report a breach
- `GET /health` - Health check

## Regulatory Compliance

- FCA CASS 15 segregation requirements
- PS10/15 safeguarding method (a) - segregated accounts
- T+1 business day safeguarding timeline
- Penny-exact (GBP 0.01) reconciliation tolerance
- 1 business day FCA breach notification

## Project Structure

```
app/
  api/          # FastAPI route handlers
  models/       # SQLAlchemy ORM models
  schemas/      # Pydantic v2 schemas
  services/     # Business logic layer
  integrations/ # External service clients
  mcp/          # MCP tool server + tools
tests/          # pytest test suite
alembic/        # Database migrations
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| DATABASE_URL | - | PostgreSQL connection string |
| REDIS_URL | redis://localhost:6379 | Redis connection |
| CLICKHOUSE_URL | - | ClickHouse for audit trail |
| MIDAZ_API_URL | - | Midaz GL ledger API |
| SERVICE_PORT | 8094 | HTTP port |

## License

Proprietary - Banxe Ltd.
