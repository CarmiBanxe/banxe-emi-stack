# STUB-INVENTORY.md — banxe-emi-stack
# Sprint 14 Task S14-01 | Auditor: Claude Code (Sonnet 4.6) + Moriel Carmi
# Date: 2026-04-13

---

## Overview

Full inventory of all stubs, mocks, in-memory adapters, `# pragma: no cover` blocks,
and `raise NotImplementedError` occurrences in the production codebase.

**Scope:** `services/`, `api/` (excluding `tests/` and `services/safeguarding-engine/`)

| Category | Count |
|----------|-------|
| `# pragma: no cover` classes/blocks | 9 |
| `raise NotImplementedError` (non-safeguarding) | 3 |
| Stub classes (`Stub*`, `StubNCA*`, etc.) | 4 |
| Mock classes (`Mock*`) | 6 |
| InMemory classes (`InMemory*`) | 19 |
| **Total entries** | **41** |

---

## Part A — `# pragma: no cover` Blocks

| # | File | Class / Block | Reason | Blocker | Unblock action |
|---|------|---------------|--------|---------|----------------|
| 1 | `services/agreement/agreement_service.py:212` | `DocuSignStub` | External API key not provisioned | BT-001 CEO | Provision DocuSign API key; implement `POST /envelopes` |
| 2 | `services/reporting/regdata_return.py:114` | `RealFIN060Generator` | WeasyPrint + FCA infra dependency | ADR-006 | Provision FCA RegData credentials; activate in prod |
| 3 | `services/reporting/regdata_return.py:145` | `LiveRegDataClient` | FCA RegData submission API not provisioned | Compliance | FCA API credentials + RegData endpoint |
| 4 | `services/events/event_bus.py:177` | `RabbitMQEventBus` | RabbitMQ broker not deployed in dev/CI | DevOps | Deploy RabbitMQ; integrate in CI with `testcontainers` |
| 5 | `services/complaints/complaint_service.py:120` | `ClickHouseComplaintRepository` | ClickHouse not in dev/CI | DevOps | `testcontainers-clickhouse` in integration test suite |
| 6 | `services/resolution/resolution_pack.py:127` | `ClickHouseResolutionRepository` | ClickHouse not in dev/CI | DevOps | Same as above |
| 7 | `services/notifications/sendgrid_adapter.py:31` | `SendGridAdapter` | SendGrid API key not provisioned in CI | DevOps | Set `SENDGRID_API_KEY` in CI secrets |
| 8 | `services/experiment_copilot/store/audit_trail.py:107` | `delete_entries()` method | Admin-only method, excluded from test coverage | None | Add unit test with `InMemoryAuditTrail` |
| 9 | `api/routers/ledger.py:80-129` | Midaz live client call blocks | Midaz prod not deployed | BT-002 DevOps | Deploy Midaz on GMKtec; remove pragmas |

---

## Part B — `raise NotImplementedError` (services, non-safeguarding)

| # | File | Class / Function | Reason | Blocker | Unblock action |
|---|------|-----------------|--------|---------|----------------|
| 10 | `services/fraud/sardine_adapter.py:66` | `SardineFraudAdapter.score()` | Sardine.ai API keys not provisioned | CEO (sales@sardine.ai) | Provision `SARDINE_CLIENT_ID` + `SARDINE_SECRET_KEY`; implement HTTP call |
| 11 | `services/reporting/regdata_return.py:152` | `LiveRegDataClient.submit()` | FCA RegData API not provisioned | Compliance | Same as row 3 above |
| 12 | `services/agreement/agreement_service.py:219` | `DocuSignStub.sign()` | DocuSign API not provisioned | BT-001 CEO | Same as row 1 above |

---

## Part C — Stub Classes

| # | File | Class | Replaces | Blocker | Unblock action |
|---|------|-------|----------|---------|----------------|
| 13 | `services/ledger/midaz_adapter.py:290` | `StubLedgerAdapter` | Live Midaz GL adapter | BT-002 DevOps (GMKtec) | Deploy Midaz; switch `LEDGER_ADAPTER=midaz` |
| 14 | `services/aml/sar_service.py:159` | `StubNCAClient` | NCA GoAML SAR submission API | Compliance | NCA GoAML API credentials; implement `submit_sar()` |
| 15 | `services/reporting/regdata_return.py:99` | `MockFIN060Generator` | Live FIN060 regulatory return | Compliance | Same as `RealFIN060Generator` above |
| 16 | `services/reporting/regdata_return.py:132` | `StubRegDataClient` | FCA RegData submission client | Compliance | FCA API credentials; replace with `LiveRegDataClient` |

---

## Part D — Mock Classes

| # | File | Class | Replaces | Blocker | Unblock action |
|---|------|-------|----------|---------|----------------|
| 17 | `services/iam/mock_iam_adapter.py:88` | `MockIAMAdapter` | Keycloak JWKS live validation | BT-003 DevOps | Deploy Keycloak prod realm; set `IAM_ADAPTER=keycloak` |
| 18 | `services/case_management/mock_case_adapter.py:24` | `MockCaseAdapter` | Marble AML case API | BT-004 CEO/Compliance | Provision Marble API key; set `CASE_ADAPTER=marble` |
| 19 | `services/fraud/mock_fraud_adapter.py:80` | `MockFraudAdapter` | Sardine.ai live scoring | CEO | Same as row 10 |
| 20 | `services/payment/mock_payment_adapter.py:53` | `MockPaymentAdapter` | Live payment rail (n8n/Modulr) | DevOps | Wire `PAYMENT_ADAPTER=modulr`; provision Modulr API key |
| 21 | `services/kyc/mock_kyc_workflow.py:79` | `MockKYCWorkflow` | ComplyAdvantage / real KYC API | DevOps/CEO | Provision KYC provider API; implement `KycWorkflowAdapter` |
| 22 | `services/recon/fca_regdata_client.py:153` | `MockFCARegDataClient` | FCA RegData live client | Compliance | FCA API credentials (same as row 3) |

---

## Part E — InMemory Classes

| # | File | Class | Replaces | Blocker | Unblock action |
|---|------|-------|----------|---------|----------------|
| 23 | `services/agreement/agreement_service.py:71` | `InMemoryAgreementService` | DB-backed agreement store | None (DB available) | Wire `AGREEMENT_SERVICE=db`; implement `DbAgreementService` |
| 24 | `services/customer/customer_service.py:62` | `InMemoryCustomerService` | DB-backed customer store | None | Already partially wired; add `DbCustomerService` |
| 25 | `services/events/event_bus.py:129` | `InMemoryEventBus` | RabbitMQ event bus | DevOps (RabbitMQ) | Deploy RabbitMQ; switch `EVENT_BUS=rabbitmq` |
| 26 | `services/transaction_monitor/store/alert_store.py:34` | `InMemoryAlertStore` | DB-backed alert store | None | Implement `DbAlertStore` backed by PostgreSQL |
| 27 | `services/transaction_monitor/scoring/velocity_tracker.py:43` | `InMemoryVelocityTracker` | Redis/DB velocity tracker | DevOps (Redis) | Deploy Redis; implement `RedisVelocityTracker` |
| 28 | `services/recon/clickhouse_client.py:225` | `InMemoryReconClient` | ClickHouse reconciliation DB | DevOps | Deploy ClickHouse; `testcontainers` in CI |
| 29 | `services/compliance_kb/storage/chroma_store.py:58` | `InMemoryChromaStore` | ChromaDB vector store | None (ChromaDB available) | Already wired; `InMemory` used only in tests |
| 30 | `services/repo_watch/store.py:91` | `InMemoryRepoWatchStore` | DB-backed repo-watch store | None | Implement `DbRepoWatchStore` |
| 31 | `services/repo_watch/github_client.py:180` | `InMemoryGitHubClient` | Live GitHub API client | None | Wire `GITHUB_TOKEN`; existing `GitHubClient` handles it |
| 32 | `services/repo_watch/notifier.py:145` | `InMemoryNotifier` | Slack / Telegram notifier | DevOps | Configure `SLACK_WEBHOOK_URL` or Telegram bot token |
| 33 | `services/statements/statement_service.py:164` | `InMemoryTransactionRepository` | DB-backed tx repository | None | Implement `DbTransactionRepository` |
| 34 | `services/agent_routing/telemetry.py:27` | `InMemoryClickHouse` | ClickHouse telemetry backend | DevOps | Deploy ClickHouse; implement live adapter |
| 35 | `services/resolution/resolution_pack.py:96` | `InMemoryResolutionRepository` | ClickHouse resolution store | DevOps | Deploy ClickHouse; activate `ClickHouseResolutionRepository` |
| 36 | `services/webhooks/webhook_router.py:268` | `InMemoryWebhookAuditStore` | DB-backed webhook audit | None | Implement `DbWebhookAuditStore` backed by PostgreSQL |
| 37 | `services/transaction_monitor/consumer/event_consumer.py:33` | `InMemoryStreamPort` | Kafka/RabbitMQ stream consumer | DevOps | Deploy message broker; implement `KafkaStreamPort` |
| 38 | `services/aml/tx_monitor.py:144` | `InMemoryVelocityTracker` | Redis velocity tracker (AML) | DevOps (Redis) | Same as row 27 |
| 39 | `services/config/config_service.py:131` | `InMemoryConfigStore` | DB-backed config store | None | Implement `DbConfigStore` backed by PostgreSQL |
| 40 | `services/compliance_kb/embeddings/embedding_service.py:39` | `InMemoryEmbeddingService` | OpenAI / local embedding model | None | Wire `EMBEDDING_ADAPTER=openai`; key already available |
| 41 | `services/experiment_copilot/agents/experiment_designer.py:45` | `InMemoryKBPort` | Live ComplianceKBService | None | Wire `ExperimentDesigner` to `ComplianceKBService` |

---

## Summary by Blocker

| Blocker | Rows | Description |
|---------|------|-------------|
| BT-001 DocuSign (CEO) | 1, 12 | e-signature API key |
| BT-002 Midaz/GMKtec (DevOps) | 9, 13 | Ledger GL server deployment |
| BT-003 Keycloak (DevOps) | 17 | IAM production realm |
| BT-004 Marble (CEO/Compliance) | 18 | AML case management API |
| CEO (Sardine.ai) | 10, 19 | Fraud scoring API keys |
| Compliance (FCA/NCA) | 11, 14, 15, 16, 22 | Regulatory submission APIs |
| DevOps (infra) | 4, 5, 6, 7, 9, 20, 25, 27, 28, 30, 32, 33, 34, 36, 37, 38 | RabbitMQ, ClickHouse, Redis, SendGrid |
| None (code only) | 8, 23, 24, 26, 29, 35, 39, 40, 41 | Implement DB/production adapter |

---

## Safeguarding Engine (separate micro-service, `services/safeguarding-engine/`)

The safeguarding engine is a separate FastAPI micro-service with its own scaffold.
All 35+ `raise NotImplementedError("Implement in Phase 3.6")` occurrences in
`services/safeguarding-engine/app/` are tracked separately — these are deliberate
scaffolding stubs for Phase 3.6 implementation.

See Sprint backlog for Phase 3.6 implementation scope.
