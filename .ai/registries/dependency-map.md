# Dependency Map — banxe-emi-stack
# Source: requirements.txt, requirements-compliance.txt, pyproject.toml, docker compose files
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: All dependencies — Python, Docker, external services

## Python dependencies (requirements.txt)

### Runtime

| Package | Version | Purpose | IL |
|---------|---------|---------|-----|
| fastapi | ≥0.111.0 | REST API framework | IL-046 |
| uvicorn[standard] | ≥0.29.0 | ASGI server | IL-046 |
| pydantic | ≥2.0.0 | Data validation (Decimal-safe) | IL-046 |
| httpx | ≥0.27.0 | Async HTTP client (Midaz CBS) | IL-012 |
| clickhouse-driver | ≥0.2.9 | ClickHouse audit trail | IL-013 |
| dbt-clickhouse | ≥1.8.0 | dbt transformations | IL-015 |
| weasyprint | ≥62.3 | FIN060 PDF generation | IL-015 |
| redis | ≥5.0.0 | Velocity tracking | IL-048 |
| pika | ≥1.3.0 | RabbitMQ event bus | IL-053 |
| psycopg2-binary | ≥2.9.9 | PostgreSQL config store | IL-053 |
| pyyaml | ≥6.0 | YAML config store | IL-040 |

### Dev/test

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ≥8.0 | Test framework |
| pytest-asyncio | ≥0.23 | Async test support |
| fakeredis | ≥2.21.0 | Redis mock |

## Compliance pipeline dependencies (requirements-compliance.txt)

| Package | Version | Purpose |
|---------|---------|---------|
| pypdf | ≥4.0.0 | PDF parsing |
| python-docx | ≥1.1.0 | DOCX parsing |
| chromadb | ≥0.5.0 | Vector DB (compliance KB) |
| sentence-transformers | ≥3.0.0 | Embeddings (all-MiniLM-L6-v2) |
| google-auth | ≥2.30.0 | Google Drive API (optional) |
| google-api-python-client | ≥2.130.0 | Google Drive API |
| google-auth-httplib2 | ≥0.2.0 | Google Drive API |
| tqdm | ≥4.66.0 | Progress bars |

## Docker images (from docker/ compose files)

| Service | Image | Port | Compose file |
|---------|-------|------|-------------|
| PostgreSQL 17 | postgres:17 | :5432 | docker-compose.recon.yml |
| ClickHouse | clickhouse/clickhouse-server | :9000 | docker-compose.recon.yml |
| Frankfurter FX | hakanensari/frankfurter:latest | :8080 | (standalone docker run) |
| adorsys mock-ASPSP | adorsys/xs2a-aspsp-mock | :8090 | docker-compose.psd2.yml |
| adorsys open-banking-gateway | adorsys/open-banking-gateway | :8888 | docker-compose.psd2.yml |
| PSD2 PostgreSQL | postgres:15 | :5434 | docker-compose.psd2.yml |
| dbt-clickhouse | (build from dbt/) | — | docker-compose.reporting.yml |

## External services (deployed on GMKtec)

| Service | Port | Adapter | Status |
|---------|------|---------|--------|
| Midaz Ledger | :8095 | services/ledger/midaz_client.py | ✅ Running |
| Keycloak | :8180 | services/iam/ | ✅ Running |
| Redis | :6379 | redis package | ✅ Running |
| RabbitMQ | :3004 | pika package | ✅ Running |
| Jube (fraud rules) | :5001 | services/fraud/jube_adapter.py | ✅ Running |
| Marble (case mgmt) | :5002/:5003 | services/case_management/marble_adapter.py | ✅ Running |
| Ballerine (KYC) | :3000 | infra/ballerine/ | ✅ Running |
| n8n (workflows) | :5678 | n8n webhooks | ✅ Running |
| Mock ASPSP | :8888 | services/recon/mock_aspsp.py | ✅ Running |

## External SaaS (blocked / not yet integrated)

| Service | Status | Blocker |
|---------|--------|---------|
| Modulr Finance (payment rails) | 🔒 | BT-001: CEO registration |
| Companies House API | 🔒 | BT-002: API key |
| OpenCorporates | 🔒 | BT-003: API key |
| Sardine.ai (fraud) | 🔒 | BT-004: API key |
| Sumsub (IDV) | 🔒 | BT-004: APP_TOKEN |
| SendGrid (email) | 🔒 | API key needed |
| Twilio (SMS) | 🔒 | ACCOUNT_SID needed |

## MCP servers

| Server | Command | Purpose |
|--------|---------|---------|
| LucidShark | `lucidshark serve --mcp .` | Code quality scanning |

## Quality tools

| Tool | Config file | Purpose |
|------|------------|---------|
| Ruff | pyproject.toml | Linting + formatting |
| Semgrep | .semgrep/banxe-rules.yml | Security rules (10 custom) |
| pytest | pyproject.toml | Testing (995 tests, coverage ≥80%) |
| pre-commit | .pre-commit-config.yaml | Git hooks |
| dbt | dbt/dbt_project.yml | Data transformations |
| LucidShark | .claude/skills/lucidshark/ | AI code scanning |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
