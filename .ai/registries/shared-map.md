# Shared Map — banxe-emi-stack
# Source: services/config/, services/events/, services/providers/, .env.example
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Shared infrastructure, event bus, config, and cross-cutting concerns

## Shared infrastructure services

### Config Store (`services/config/` — 4 files)
- Pattern: Config-as-Data (Geniusto v5 Pattern #6, IL-040)
- `config_port.py` — ConfigPort protocol (abstract)
- `config_service.py` — YAMLConfigStore with runtime reload
- Data file: `config/banxe_config.yaml` — products, fees, limits
- No code deploy needed — YAML changes picked up at runtime

### Event Bus (`services/events/` — 2 files)
- Backend: RabbitMQ (:3004 on GMKtec)
- `event_bus.py` — publish/subscribe, domain events
- Used by: payment audit trail, compliance alerts, notification triggers

### Provider Registry (`services/providers/` — 2 files)
- Pattern: Plugin Architecture (Geniusto v5 Plugin2/Provider2)
- `provider_registry.py` — runtime provider discovery and health checks
- Config: `config/providers.yaml` — primary/fallback/sandbox per category
- Categories: payment_rails, idv, fraud, kyb, notification, iam

### Notification Service (`services/notifications/` — 5 files)
- `notification_port.py` — NotificationPort protocol
- `notification_service.py` — orchestrator
- `sendgrid_adapter.py` — Email (SendGrid)
- `mock_notification_adapter.py` — Test/dev adapter
- Channels: Email (SendGrid), SMS (Twilio), Telegram (MLRO alerts)

### Webhook Router (`services/webhooks/` — 2 files)
- `webhook_router.py` — inbound webhook routing
- Handles: Modulr payment webhooks, Watchman list updates

## Provider matrix (from config/providers.yaml)

| Category | Primary | Fallback | Sandbox |
|----------|---------|----------|---------|
| Payment Rails | Modulr (🔒 BT-001) | ClearBank (disabled) | MockPaymentAdapter ✅ |
| IDV (KYC) | Sumsub (🔒 BT-004) | Onfido (disabled) | MockKYCWorkflow ✅ |
| Fraud | Sardine.ai (🔒 BT-009) | — | MockFraudAdapter ✅ |
| KYB | Companies House (🔒 BT-005) | — | MockKYBAdapter ✅ |
| Notification | SendGrid / Twilio | Telegram | Telegram ✅ |
| IAM | Keycloak OIDC | — | MockIAMAdapter ✅ |

## Shared databases

| Database | Engine | Port | Purpose | Retention |
|----------|--------|------|---------|-----------|
| `banxe_compliance` | PostgreSQL 17 | :5432 | Primary OLTP, pgAudit | Standard |
| `banxe` | ClickHouse | :9000 | Audit trail, analytics | 5 years (I-08) |
| Redis | Redis | :6379 | Velocity tracking, caching | Session |
| RabbitMQ | RabbitMQ | :3004 | Event bus | Message TTL |

## Shared tables (ClickHouse)

| Table | Purpose | Write policy |
|-------|---------|-------------|
| `safeguarding_events` | Daily recon results | Append-only (I-24) |
| `safeguarding_breaches` | Breach detection alerts | Append-only |
| `payment_events` | Payment audit trail | Append-only |
| `compliance_swarm_events` | AI agent audit | Append-only |

## Environment variables (shared, from .env.example)

| Category | Variables | Count |
|----------|-----------|-------|
| Midaz CBS | MIDAZ_BASE_URL, MIDAZ_ORG_ID, MIDAZ_LEDGER_ID, MIDAZ_TOKEN | 4 |
| Safeguarding accounts | SAFEGUARDING_CLIENT_FUNDS_ACCOUNT, SAFEGUARDING_OPERATIONAL_ACCOUNT | 2 |
| PostgreSQL | POSTGRES_HOST/PORT/DB/USER/PASSWORD | 5 |
| ClickHouse | CLICKHOUSE_HOST/PORT/DB/USER/PASSWORD | 5 |
| Redis | REDIS_URL | 1 |
| n8n | N8N_WEBHOOK_URL | 1 |
| Bank statements | STATEMENT_DIR, ADORSYS_PSD2_URL, IBANs | 5 |
| FX | FRANKFURTER_URL | 1 |
| dbt | DBT_PROFILES_DIR, DBT_TARGET | 2 |
| FCA Reporting | FCA_REGDATA_URL, FIN060_OUTPUT_DIR | 2 |
| Reconciliation | RECON_THRESHOLD_GBP, RECON_CURRENCY | 2 |
| **Total** | | **30** |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
