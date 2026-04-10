# Dependency Map — banxe-emi-stack
# Source: requirements.txt, requirements-compliance.txt, pyproject.toml, docker/ (FUNCTION 1 scan)
# Created: 2026-04-10 | Updated: 2026-04-10 (post-Phase 6 scan)
# Purpose: All dependencies — Python, Docker, external services, env vars

## Python dependencies (requirements.txt — runtime)

| Package | Version | Purpose | Used by | IL |
|---------|---------|---------|---------|-----|
| fastapi | ≥0.111.0 | REST API framework | api/ | IL-046 |
| uvicorn[standard] | ≥0.29.0 | ASGI server | main.py | IL-046 |
| pydantic | ≥2.0.0 | Data validation (Decimal-safe, str amounts) | all | IL-046 |
| httpx | ≥0.27.0 | Async HTTP client | all adapters | IL-012 |
| clickhouse-driver | ≥0.2.9 | ClickHouse audit trail | recon, customer | IL-013 |
| dbt-clickhouse | ≥1.8.0 | FIN060 data transforms | reporting | IL-015 |
| weasyprint | ≥62.3 | FIN060 PDF generation | reporting | IL-015 |
| redis | ≥5.0.0 | Velocity tracking (AML) | aml/ | IL-048 |
| pika | ≥1.3.0 | RabbitMQ event bus | events/ | IL-053 |
| psycopg2-binary | ≥2.9.9 | PostgreSQL config store | config/ | IL-053 |
| pyyaml | ≥6.0 | YAML config store | config/ | IL-040 |

## Python dependencies (requirements-compliance.txt — compliance pipeline)

| Package | Version | Purpose |
|---------|---------|---------|
| pypdf | ≥4.0.0 | Compliance document parsing (PDF) |
| python-docx | ≥1.1.0 | Compliance document parsing (DOCX) |
| chromadb | ≥0.5.0 | Vector DB (compliance KB, 476 chunks) |
| sentence-transformers | ≥3.0.0 | Embeddings (all-MiniLM-L6-v2, 16 domains) |
| google-auth | ≥2.30.0 | Google Drive API (optional — doc ingestion) |
| google-api-python-client | ≥2.130.0 | Google Drive API |
| google-auth-httplib2 | ≥0.2.0 | Google Drive HTTP transport |
| tqdm | ≥4.66.0 | Progress bars (ingestion pipeline) |

## Dev/test dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ≥8.0 | Test framework |
| pytest-asyncio | ≥0.23 | Async test support |
| pytest-cov | ≥7.1 | Coverage (threshold: 80%, actual: 86.89%) |
| pytest-timeout | ≥2.4 | Pre-commit hook timeout |
| fakeredis | ≥2.21.0 | Redis mock (test_redis_velocity_tracker.py) |

## Docker services (from docker/ compose files)

| Service | Image | Port | Compose file | Status |
|---------|-------|------|-------------|--------|
| postgres | pgvector/pgvector:pg17 | 5432 | docker-compose.recon.yml | Always-on |
| clickhouse | clickhouse/clickhouse-server:24.3 | 8123, 9000 | docker-compose.recon.yml | Always-on |
| redis | redis:7-alpine | 6379 | docker-compose.recon.yml | Always-on |
| n8n | n8nio/n8n:latest | 5678 | docker-compose.recon.yml | Always-on |
| frankfurter | hakanensari/frankfurter | 8181 | docker-compose.recon.yml | Always-on |
| dbt | ghcr.io/dbt-labs/dbt-clickhouse:1.8.0 | — | docker-compose.reporting.yml | On-demand |
| fin060-generator | Custom (Dockerfile.reporting) | — | docker-compose.reporting.yml | On-demand |
| mock-aspsp | Custom (Dockerfile.mock-aspsp) | 8888 | docker-compose.psd2.yml | On-demand |

## External services — API dependencies

| Service | Provider | Endpoint | Auth | Status | Module |
|---------|----------|----------|------|--------|--------|
| Jube (fraud ML) | Self-hosted | http://gmktec:5001 | Bearer | ACTIVE | services/fraud/ |
| Sardine.ai (fraud) | Sardine | https://api.sardine.ai/v1 | HTTP Basic | STUB | services/fraud/ |
| Modulr (payments) | Modulr Finance | https://api-sandbox.modulrfinance.com | API key | ACTIVE | services/payment/ |
| Balleryne (KYC) | Balleryne | http://gmktec:3000 | Bearer | STUB | services/kyc/ |
| Marble (cases) | Checkmarble | https://checkmarble.com | Bearer | STUB | services/case_management/ |
| Keycloak (IAM) | Self-hosted | http://gmktec:8180 | OAuth2 | STUB | services/iam/ |
| Midaz (CBS ledger) | Self-hosted | http://localhost:8095 | Bearer | STUB | services/ledger/ |
| Watchman (sanctions) | Moov / Self-hosted | webhook inbound | HMAC | STUB | api/routers/watchman_webhook.py |
| SendGrid (email) | Twilio SendGrid | https://api.sendgrid.com | API key | ACTIVE | services/notifications/ |
| n8n (workflows) | Self-hosted | http://localhost:5678 | Webhook | ACTIVE | services/complaints/ |
| Frankfurter (FX) | Self-hosted (ECB) | http://localhost:8181 | — | ACTIVE | docker/ |
| ClickHouse (audit) | Self-hosted | localhost:9000 | user/password | PARTIAL | services/recon/ |
| PostgreSQL (config) | Self-hosted | localhost:5432 | user/password | ACTIVE | services/config/ |
| mock-ASPSP (PSD2) | Self-hosted | http://localhost:8888 | OAuth2 | ACTIVE (mock) | services/recon/ |
| NCA SAROnline | NCA | (not configured) | — | STUB | services/aml/sar_service.py |

## Environment variables required

### Core API
```
PORT=8000
SECRET_KEY=<jwt signing key>
```

### Payment
```
MODULR_API_KEY=<key>
MODULR_API_SECRET=<secret>
MODULR_BASE_URL=https://api-sandbox.modulrfinance.com
```

### Fraud / AML
```
FRAUD_ADAPTER=jube|sardine|mock
JUBE_API_KEY=<key>
JUBE_BASE_URL=http://gmktec:5001
SARDINE_CLIENT_ID=<id>         # CEO action — BLOCKED
SARDINE_SECRET_KEY=<key>       # CEO action — BLOCKED
VELOCITY_TRACKER=redis|memory
REDIS_URL=redis://localhost:6379
```

### KYC / Case Management
```
BALLERYNE_URL=http://gmktec:3000
BALLERYNE_API_KEY=<key>
MARBLE_API_KEY=<key>            # Ops action — BLOCKED
COMPANIES_HOUSE_API_KEY=<key>   # Ops action — BLOCKED
OPENCORPORATES_API_KEY=<key>    # Ops action — BLOCKED
```

### IAM
```
KEYCLOAK_URL=http://gmktec:8180
KEYCLOAK_REALM=banxe
KEYCLOAK_CLIENT_ID=banxe-api
KEYCLOAK_CLIENT_SECRET=<secret>
```

### Ledger / CBS
```
MIDAZ_BASE_URL=http://localhost:8095
MIDAZ_TOKEN=<bearer token>
```

### Notifications
```
SENDGRID_API_KEY=<key>
SENDGRID_FROM_EMAIL=noreply@banxe.com
```

### Infrastructure
```
POSTGRES_URL=postgresql://user:pass@localhost:5432/banxe
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=9000
CLICKHOUSE_DB=banxe
CLICKHOUSE_USER=<user>
CLICKHOUSE_PASSWORD=<password>
N8N_WEBHOOK_URL=http://localhost:5678/webhook
RABBITMQ_URL=amqp://guest:guest@localhost:5672/
FRANKFURTER_URL=http://localhost:8181
```

### Compliance KB (RAG)
```
CHROMA_PATH=./compliance_vectordb
RAG_COLLECTION=banxe_compliance_kb
RAG_EMBED_MODEL=all-MiniLM-L6-v2
```

## Internal service dependencies

```
api/ ──────────► services/fraud/          ──► services/aml/
     ──────────► services/kyc/            ──► services/hitl/
     ──────────► services/payment/        ──► services/events/
     ──────────► services/customer/       ──► services/notifications/
     ──────────► services/reporting/      ──► services/recon/
     ──────────► services/hitl/           ──► services/case_management/
     ──────────► services/notifications/
     ──────────► services/ledger/
     ──────────► services/consumer_duty/

agents/compliance/ ──► services/aml/      (tool: sar_service)
                   ──► services/hitl/     (tool: hitl_check_gate)
                   ──► services/case_management/ (tool: marble_create_case)
```

---

*Last updated: 2026-04-10 (FUNCTION 1 scan — post-Phase 6)*
