# API Map — banxe-emi-stack
# Source: api/routers/, api/models/, services/payment/openapi.yml
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: All API endpoints, methods, models, auth

## Overview

- Framework: FastAPI (IL-046)
- Entrypoint: `api/main.py`
- Dependencies: `api/deps.py`
- Total endpoints: 42
- Auth: Keycloak OIDC (7 roles, realm: banxe)

## Endpoints by router

### Health (`api/routers/health.py`)
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |
| GET | `/health/ready` | Readiness check |

### Customers (`api/routers/customers.py`) — model: `api/models/customers.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/customers` | Create customer |
| GET | `/customers` | List customers |
| GET | `/customers/{id}` | Get customer by ID |
| POST | `/customers/{id}/...` | Customer operation |

### Payments (`api/routers/payments.py`) — model: `api/models/payments.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/payments` | Create payment intent |
| GET | `/payments` | List payments |
| GET | `/payments/{id}` | Get payment by ID |

### Ledger (`api/routers/ledger.py`) — model: `api/models/ledger.py`
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/ledger/balances` | Get account balances (Midaz) |
| GET | `/ledger/transactions` | List transactions |

### KYC (`api/routers/kyc.py`) — model: `api/models/kyc.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/kyc/verify` | Start KYC verification |
| GET | `/kyc/{id}` | Get KYC status |
| POST | `/kyc/{id}/documents` | Upload KYC documents |
| POST | `/kyc/{id}/decision` | Manual KYC decision |
| POST | `/kyc/{id}/...` | Additional KYC operation |

### Fraud (`api/routers/fraud.py`) — model: `api/models/fraud.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/fraud/check` | Run fraud check on transaction |

### HITL (`api/routers/hitl.py`) — model: `api/models/hitl.py`
| Method | Path | Purpose |
|--------|------|---------|
| GET | `/hitl/proposals` | List pending HITL proposals |
| POST | `/hitl/proposals/{id}/decide` | Approve/reject proposal |
| GET | `/hitl/feedback` | List feedback entries |
| POST | `/hitl/feedback` | Submit HITL feedback |
| GET | `/hitl/stats` | HITL statistics |

### Reporting (`api/routers/reporting.py`) — model: `api/models/reporting.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/reporting/fin060` | Generate FIN060 return |
| POST | `/reporting/sar` | File SAR report |
| POST | `/reporting/consumer-duty` | Generate consumer duty report |
| GET | `/reporting/fin060/{id}` | Get FIN060 status |
| GET | `/reporting/sar/{id}` | Get SAR status |
| GET | `/reporting/consumer-duty/{id}` | Get consumer duty report |
| POST | `/reporting/...` | Additional reporting endpoints (3) |

### Consumer Duty (`api/routers/consumer_duty.py`) — model: `api/models/consumer_duty.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/consumer-duty/assess` | Assess consumer duty compliance |
| GET | `/consumer-duty/assessments` | List assessments |
| POST | `/consumer-duty/complaints` | Submit consumer duty complaint |
| POST | `/consumer-duty/outcomes` | Record outcome |
| POST | `/consumer-duty/...` | Additional endpoint |

### Notifications (`api/routers/notifications.py`) — model: `api/models/notifications.py`
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/notifications` | Send notification |
| GET | `/notifications` | List notifications |
| GET | `/notifications/{id}` | Get notification details |

### MLRO Notifications (`api/routers/mlro_notifications.py`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/mlro/notifications` | Send MLRO-specific alert |

### Sanctions Rescreen (`api/routers/sanctions_rescreen.py`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sanctions/rescreen` | Trigger sanctions rescreen |

### Watchman Webhook (`api/routers/watchman_webhook.py`)
| Method | Path | Purpose |
|--------|------|---------|
| POST | `/webhooks/watchman` | Receive watchman list update |

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

7 roles defined in `config/keycloak-realm.json` (IL-039).
Specific role assignments per endpoint TBD in production.

---
*Last updated: 2026-04-10 (Phase 4 migration)*
