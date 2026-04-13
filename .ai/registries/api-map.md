# API Map — banxe-emi-stack
# Source: api/routers/, api/models/, api/main.py, services/payment/openapi.yml
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14: 78 endpoints, 2619 tests, 87% coverage)
# Migration Phase: 14
# Purpose: All API endpoints with exact paths, methods, models, auth

## Overview

- Framework: FastAPI (IL-046)
- Entrypoint: `api/main.py`
- Dependencies: `api/deps.py`
- Total endpoints: 78
- Auth: Keycloak OIDC (7 roles, realm: banxe)
- Base prefix: `/v1` (applied via `app.include_router(..., prefix="/v1")` for most routers)

## Router prefix rules (from api/main.py lines 101-115)

| Router | Prefix applied in main.py | Effective base path |
|--------|--------------------------|-------------------|
| health | (none) | / |
| customers | /v1 | /v1/customers |
| kyc | /v1 | /v1/kyc |
| payments | /v1 | /v1/payments |
| ledger | /v1 | /v1/ledger |
| notifications | /v1 | /v1/notifications |
| fraud | /v1 | /v1/fraud |
| consumer_duty | /v1 | /v1/consumer-duty |
| hitl | /v1 | /v1/hitl |
| reporting | /v1 | /v1/reporting |
| watchman_webhook | (none) | /webhooks (router-level prefix) |
| mlro_notifications | (none) | /internal/notifications (router-level prefix) |
| sanctions_rescreen | (none) | /compliance/sanctions (router-level prefix) |

## Endpoints by router (exact paths as served)

### Health (`api/routers/health.py`) — no /v1 prefix
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 1 | GET | `/health` | Liveness check |
| 2 | GET | `/health/ready` | Readiness check |

### Customers (`api/routers/customers.py`) — model: `api/models/customers.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 3 | POST | `/v1/customers` | Create customer |
| 4 | GET | `/v1/customers` | List customers |
| 5 | GET | `/v1/customers/{customer_id}` | Get customer by ID |
| 6 | POST | `/v1/customers/{customer_id}/lifecycle` | Customer lifecycle operation |

### Payments (`api/routers/payments.py`) — model: `api/models/payments.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 7 | POST | `/v1/payments` | Create payment intent |
| 8 | GET | `/v1/payments` | List payments |
| 9 | GET | `/v1/payments/{idempotency_key}` | Get payment by idempotency key |

### Ledger (`api/routers/ledger.py`) — model: `api/models/ledger.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 10 | GET | `/v1/ledger/accounts` | List ledger accounts (Midaz CBS) |
| 11 | GET | `/v1/ledger/accounts/{account_id}/balance` | Get account balance |

### KYC (`api/routers/kyc.py`) — model: `api/models/kyc.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 12 | POST | `/v1/kyc/workflows` | Start KYC workflow |
| 13 | GET | `/v1/kyc/workflows/{workflow_id}` | Get KYC workflow status |
| 14 | POST | `/v1/kyc/workflows/{workflow_id}/documents` | Upload KYC documents |
| 15 | POST | `/v1/kyc/workflows/{workflow_id}/approve-edd` | Approve EDD |
| 16 | POST | `/v1/kyc/workflows/{workflow_id}/reject` | Reject KYC workflow |

### Fraud (`api/routers/fraud.py`) — model: `api/models/fraud.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 17 | POST | `/v1/fraud/assess` | Run fraud assessment |

### HITL (`api/routers/hitl.py`) — model: `api/models/hitl.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 18 | GET | `/v1/hitl/queue` | List pending HITL cases |
| 19 | POST | `/v1/hitl/queue` | Create HITL case |
| 20 | GET | `/v1/hitl/queue/{case_id}` | Get HITL case detail |
| 21 | POST | `/v1/hitl/queue/{case_id}/decide` | Approve/reject HITL case |
| 22 | GET | `/v1/hitl/stats` | HITL statistics |

### Reporting (`api/routers/reporting.py`) — model: `api/models/reporting.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 23 | POST | `/v1/reporting/fin060/generate` | Generate FIN060 return |
| 24 | POST | `/v1/reporting/fin060/submit` | Submit FIN060 to FCA |
| 25 | POST | `/v1/reporting/sar` | File SAR report |
| 26 | GET | `/v1/reporting/sar` | List SAR reports |
| 27 | GET | `/v1/reporting/sar/stats` | SAR statistics |
| 28 | GET | `/v1/reporting/sar/{sar_id}` | Get SAR detail |
| 29 | POST | `/v1/reporting/sar/{sar_id}/approve` | Approve SAR |
| 30 | POST | `/v1/reporting/sar/{sar_id}/submit` | Submit SAR to NCA |
| 31 | POST | `/v1/reporting/sar/{sar_id}/withdraw` | Withdraw SAR |

### Consumer Duty (`api/routers/consumer_duty.py`) — model: `api/models/consumer_duty.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 32 | POST | `/v1/consumer-duty/vulnerability` | Assess customer vulnerability |
| 33 | GET | `/v1/consumer-duty/vulnerability/{customer_id}` | Get vulnerability assessment |
| 34 | POST | `/v1/consumer-duty/fair-value` | Fair value assessment |
| 35 | POST | `/v1/consumer-duty/outcomes` | Record consumer outcome |
| 36 | POST | `/v1/consumer-duty/report` | Generate consumer duty report |

### Notifications (`api/routers/notifications.py`) — model: `api/models/notifications.py`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 37 | POST | `/v1/notifications/send` | Send notification |
| 38 | GET | `/v1/notifications/{notification_id}/status` | Get notification status |
| 39 | GET | `/v1/notifications/preview` | Preview notification |

### MLRO Notifications (`api/routers/mlro_notifications.py`) — router prefix: `/internal/notifications`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 40 | POST | `/internal/notifications/mlro` | Send MLRO-specific alert |

### Sanctions Rescreen (`api/routers/sanctions_rescreen.py`) — router prefix: `/compliance/sanctions`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 41 | POST | `/compliance/sanctions/rescreen/high-risk` | Trigger high-risk sanctions rescreen |

### Watchman Webhook (`api/routers/watchman_webhook.py`) — router prefix: `/webhooks`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 42 | POST | `/webhooks/watchman` | Receive watchman list update |

### Auth (`api/routers/auth.py`) — prefix: `/v1`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 43 | POST | `/v1/auth/login` | Authenticate, return JWT |

### Statements (`api/routers/statements.py`) — prefix: `/v1`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 44 | GET | `/v1/accounts/{account_id}/statement` | Download account statement (JSON) |
| 45 | GET | `/v1/accounts/{account_id}/statement/csv` | Download account statement (CSV) |

### Compliance KB (`api/routers/compliance_kb.py`) — prefix: `/v1`
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 46 | GET | `/v1/kb/search` | Search compliance knowledge base |
| 47 | POST | `/v1/kb/ingest` | Ingest compliance document |
| 48 | GET | `/v1/kb/documents` | List all KB documents |
| 49 | GET | `/v1/kb/documents/{doc_id}` | Get KB document |
| 50 | DELETE | `/v1/kb/documents/{doc_id}` | Delete KB document |
| 51 | POST | `/v1/kb/ask` | Ask compliance question (RAG) |
| 52 | GET | `/v1/kb/stats` | KB statistics |
| 53 | POST | `/v1/kb/rebuild` | Rebuild KB embeddings |

### Experiments (`api/routers/experiments.py`) — prefix: `/v1` (IL-CEC-01)
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 54 | GET | `/v1/experiments` | List experiments |
| 55 | POST | `/v1/experiments` | Create experiment |
| 56 | GET | `/v1/experiments/{experiment_id}` | Get experiment |
| 57 | PUT | `/v1/experiments/{experiment_id}` | Update experiment |
| 58 | DELETE | `/v1/experiments/{experiment_id}` | Delete experiment |
| 59 | POST | `/v1/experiments/{experiment_id}/enroll` | Enroll customer in experiment |
| 60 | GET | `/v1/experiments/{experiment_id}/results` | Get experiment results |
| 61 | POST | `/v1/experiments/{experiment_id}/conclude` | Conclude experiment |

### Transaction Monitor (`api/routers/transaction_monitor.py`) — prefix: `/v1` (IL-RTM-01)
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 62 | GET | `/v1/monitor/alerts` | List monitoring alerts |
| 63 | POST | `/v1/monitor/alerts` | Create monitoring alert |
| 64 | GET | `/v1/monitor/alerts/{alert_id}` | Get alert detail |
| 65 | POST | `/v1/monitor/alerts/{alert_id}/resolve` | Resolve alert |
| 66 | GET | `/v1/monitor/rules` | List monitoring rules |
| 67 | POST | `/v1/monitor/rules` | Create monitoring rule |
| 68 | PUT | `/v1/monitor/rules/{rule_id}` | Update monitoring rule |
| 69 | DELETE | `/v1/monitor/rules/{rule_id}` | Delete monitoring rule |

### Safeguarding (`api/routers/safeguarding.py`) — prefix: `/v1` (CASS 15)
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 70 | GET | `/v1/safeguarding/position` | Daily client funds position (CASS 7.15.17R) |
| 71 | GET | `/v1/safeguarding/accounts` | Designated safeguarding accounts list (CASS 7.13) |
| 72 | GET | `/v1/safeguarding/breaches` | Breach history log (CASS 7.15.29R) |
| 73 | POST | `/v1/safeguarding/reconcile` | Trigger daily reconciliation (CASS 7.15.17R) |
| 74 | GET | `/v1/safeguarding/resolution-pack` | Export resolution pack (CASS 15.12) |
| 75 | POST | `/v1/safeguarding/fca-return` | Generate FIN060 monthly FCA return (CASS 15.12.4R) |

### Reconciliation (`api/routers/recon.py`) — prefix: `/v1` (CASS 7.15)
| # | Method | Full path | Purpose |
|---|--------|----------|---------|
| 76 | GET | `/v1/recon/status` | Latest tri-party reconciliation status |
| 77 | GET | `/v1/recon/report` | Full tri-party recon report (3 legs) |
| 78 | GET | `/v1/recon/history` | Reconciliation history (last N days) |

## API models

| File | Domain | Key models |
|------|--------|------------|
| `api/models/customers.py` | Customer | CustomerCreate, CustomerResponse |
| `api/models/payments.py` | Payments | PaymentIntent, PaymentResult, PaymentStatus |
| `api/models/ledger.py` | Ledger | BalanceResponse, TransactionResponse |
| `api/models/kyc.py` | KYC | KYCRequest, KYCStatus, KYCDecision |
| `api/models/fraud.py` | Fraud | FraudCheckRequest, FraudCheckResult |
| `api/models/hitl.py` | HITL | HITLProposal, HITLDecision, HITLFeedback |
| `api/models/reporting.py` | Reporting | FIN060Request, SARRequest, ConsumerDutyReport |
| `api/models/consumer_duty.py` | Consumer Duty | DutyAssessment, OutcomeRecord |
| `api/models/notifications.py` | Notifications | NotificationRequest, NotificationStatus |

## Auth roles (Keycloak realm: banxe)

7 roles defined in `config/keycloak-realm.json` (IL-039):

| Role | Endpoints accessible | Notes |
|------|---------------------|-------|
| ADMIN | All 42 | Superuser |
| MLRO | HITL, reporting/sar, sanctions, mlro_notifications | Money Laundering Reporting Officer |
| COMPLIANCE_OFFICER | HITL, KYC (approve/reject), consumer-duty, fraud | Compliance team |
| CFO | reporting/fin060 | Chief Financial Officer |
| FRAUD_ANALYST | fraud/assess, HITL | Fraud team |
| OPERATOR | customers, notifications | Customer operations |
| CUSTOMER | payments, ledger, kyc (start/docs/status), notifications (status), customers (own) | End customers |

## Endpoint statistics

| Category | Count | Prefix |
|----------|-------|--------|
| Health | 2 | / (no prefix) |
| Customers | 4 | /v1 |
| Payments | 3 | /v1 |
| Ledger | 2 | /v1 |
| KYC | 5 | /v1 |
| Fraud | 1 | /v1 |
| HITL | 5 | /v1 |
| Reporting | 9 | /v1 |
| Consumer Duty | 5 | /v1 |
| Notifications | 3 | /v1 |
| MLRO Notifications | 1 | /internal (router-level) |
| Sanctions | 1 | /compliance (router-level) |
| Webhooks | 1 | /webhooks (router-level) |
| Auth | 1 | /v1 |
| Statements | 2 | /v1 |
| Compliance KB | 8 | /v1 |
| Experiments | 8 | /v1 |
| Transaction Monitor | 8 | /v1 |
| **Safeguarding (Sprint 12)** | **6** | /v1 |
| **Reconciliation (Sprint 12)** | **3** | /v1 |
| **Total** | **78** | |

---
*Last updated: 2026-04-13 (Sprint 12: safeguarding CASS 15 + tri-party recon API)*
