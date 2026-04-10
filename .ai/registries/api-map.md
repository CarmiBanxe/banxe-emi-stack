# API Map — banxe-emi-stack
# Source: api/routers/, api/models/, api/main.py, services/payment/openapi.yml
# Created: 2026-04-10 | Updated: 2026-04-10 (Phase 5 intelligence pass)
# Migration Phase: 5
# Purpose: All API endpoints with exact paths, methods, models, auth

## Overview

- Framework: FastAPI (IL-046)
- Entrypoint: `api/main.py`
- Dependencies: `api/deps.py`
- Total endpoints: 42
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
| **Total** | **42** | |

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*
