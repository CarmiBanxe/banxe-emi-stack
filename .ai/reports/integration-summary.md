# Integration Summary — banxe-emi-stack
# Source: config/providers.yaml, .env.example, agents/compliance/swarm.yaml
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: External integrations status

## Integration overview

| Category | Active | Total | Blocked |
|----------|--------|-------|---------|
| Payment rails | 1 (mock) | 3 | 2 (Modulr, ClearBank) |
| IDV / KYC | 1 (mock) + 1 (Ballerine) | 4 | 2 (Sumsub, Onfido) |
| Fraud detection | 1 (mock) + 1 (Jube) | 3 | 1 (Sardine) |
| KYB | 1 (mock) | 2 | 1 (Companies House) |
| Case management | 1 (Marble) | 1 | — |
| Notification | 1 (Telegram) | 3 | 2 (SendGrid, Twilio) |
| IAM | 1 (Keycloak) | 2 | — |
| CBS / Ledger | 1 (Midaz) | 1 | — |
| FX rates | 1 (Frankfurter) | 1 | — |
| Bank connectivity | 1 (adorsys PSD2 mock) | 1 | — |
| Audit trail | 2 (ClickHouse + pgAudit) | 2 | — |

## Active integrations (running on GMKtec)

### Self-hosted services

| Service | Port | Adapter | Health check |
|---------|------|---------|-------------|
| Midaz Ledger (CBS) | :8095 | `services/ledger/midaz_client.py` | `GET /health` |
| Keycloak OIDC | :8180 | `services/iam/` | `GET /health` |
| Redis | :6379 | `redis` package | `PING` |
| RabbitMQ | :3004 | `pika` package | Connection test |
| Jube (fraud rules) | :5001 | `services/fraud/jube_adapter.py` | `GET /health` |
| Marble (case mgmt) | :5002/:5003 | `services/case_management/marble_adapter.py` | API check |
| Ballerine (KYC) | :3000 | `infra/ballerine/` | `GET /health` |
| n8n (workflows) | :5678 | Webhook integration | `GET /healthz` |
| Frankfurter FX | :8080 | `httpx` direct | `GET /latest?from=GBP` |
| adorsys mock ASPSP | :8888 | `services/recon/statement_poller.py` | `GET /actuator/health` |
| PostgreSQL 17 | :5432 | `psycopg2-binary` | `pg_isready` |
| ClickHouse | :9000 | `clickhouse-driver` | Connection test |

### Data flows

```
Midaz CBS ──→ ReconciliationEngine ──→ ClickHouse (safeguarding_events)
                    │                         │
                    ▼                         ▼
            BreachDetector ──→ n8n ──→ Telegram (MLRO alert)
                                      │
adorsys PSD2 ──→ StatementPoller ─────┘
                                      
Jube ◄──→ FraudAMLPipeline ──→ Marble (cases)
                │
                ▼
         AML Swarm Agents ──→ ClickHouse (compliance_swarm_events)
                │
                ▼
           HITL Service ──→ MLRO/Compliance Officer review
```

## Blocked integrations

| Integration | Adapter ready | Blocker | Tracking |
|-------------|--------------|---------|----------|
| Modulr Finance (payment rails) | `services/payment/modulr_client.py` ✅ | CEO must register at modulrfinance.com/developer | BT-001 |
| ClearBank (fallback payments) | Config in providers.yaml | CLEARBANK_API_KEY | — |
| Companies House (KYB) | Config in providers.yaml | COMPANIES_HOUSE_API_KEY | BT-002 |
| OpenCorporates (KYB fallback) | Config in providers.yaml | OPENCORPORATES_API_KEY | BT-003 |
| Sardine.ai (fraud scoring) | `services/fraud/sardine_adapter.py` ✅ | SARDINE_CLIENT_ID | BT-004 |
| Sumsub (IDV) | Config in providers.yaml | SUMSUB_APP_TOKEN | BT-004 |
| Onfido (IDV fallback) | Config in providers.yaml | ONFIDO_API_TOKEN | — |
| SendGrid (email) | `services/notifications/sendgrid_adapter.py` ✅ | SENDGRID_API_KEY | — |
| Twilio (SMS) | Config in providers.yaml | TWILIO_ACCOUNT_SID | — |
| FCA RegData (FIN060 upload) | `services/reporting/regdata_return.py` ✅ | FCA_REGDATA_USER/PASSWORD | — |

## Provider architecture

Pattern: Plugin Architecture from `config/providers.yaml`
- Each category has: primary → fallback → sandbox
- Health endpoints polled at startup and every 60s
- Zero-code switch: change env var (e.g., `PAYMENT_ADAPTER=modulr`)
- All sandboxed with mock adapters for testing

## Webhooks

### Inbound
| Source | Endpoint | Handler |
|--------|----------|---------|
| Modulr (payments) | `POST /webhooks/modulr` | `services/payment/webhook_handler.py` |
| Watchman (sanctions) | `POST /webhooks/watchman` | `api/routers/watchman_webhook.py` |

### Outbound
| Target | Trigger | Handler |
|--------|---------|---------|
| n8n (safeguarding alert) | Recon DISCREPANCY | `N8N_WEBHOOK_URL` in daily-recon.sh |
| n8n (complaint) | Consumer complaint | `services/complaints/n8n_webhook.py` |
| Jube (fraud rules) | Transaction event | `services/fraud/jube_adapter.py` |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
