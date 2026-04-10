# Mobile & Web Gap Analysis — banxe-emi-stack
# Source: Gap analysis vs target architecture
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: What's missing for web/mobile apps

## Current state

banxe-emi-stack is backend-only. No web or mobile frontend exists.

### What exists (backend ready)

| Capability | API endpoint | Status |
|------------|-------------|--------|
| Customer CRUD | POST/GET /customers | ✅ |
| Payments (FPS/SEPA/BACS) | POST/GET /payments | ✅ (mock adapter) |
| Account balances | GET /ledger/balances | ✅ |
| Transactions | GET /ledger/transactions | ✅ |
| KYC verification | POST /kyc/verify | ✅ (mock adapter) |
| Notifications | POST/GET /notifications | ✅ |
| Health checks | GET /health, /health/ready | ✅ |
| Fraud check | POST /fraud/check | ✅ (mock adapter) |
| HITL review | GET/POST /hitl/proposals | ✅ |
| Reporting | POST /reporting/fin060 | ✅ |
| Swagger UI | /docs | ✅ (auto-generated) |

### External UIs (deployed but separate)

| UI | Port | Purpose | Covers |
|----|------|---------|--------|
| Ballerine Backoffice | :5137 | KYC case review | KYC ops |
| Marble | :5002/:5003 | Transaction monitoring | AML ops |
| n8n | :5678 | Workflow automation | Ops automation |
| Keycloak | :8180 | IAM admin | Auth management |

## Gaps for web app

| Gap | Priority | Effort | Notes |
|-----|----------|--------|-------|
| Frontend framework (React/Next.js) | HIGH | LARGE | No frontend code exists |
| Auth integration (Keycloak OIDC flow) | HIGH | MEDIUM | Backend ready, need frontend PKCE flow |
| Customer dashboard | HIGH | LARGE | Balance, transactions, statements |
| Payment initiation UI | HIGH | MEDIUM | FPS/SEPA form, status tracking |
| KYC onboarding flow | MEDIUM | LARGE | Document upload, liveness check |
| Compliance dashboard (internal) | MEDIUM | MEDIUM | Recon status, FIN060, SAR tracking |
| WebSocket for real-time events | MEDIUM | MEDIUM | Event bus exists (RabbitMQ) but no WS gateway |
| API rate limiting | MEDIUM | SMALL | Not currently implemented |
| CORS configuration | LOW | SMALL | FastAPI middleware needed |

## Gaps for mobile app

| Gap | Priority | Effort | Notes |
|-----|----------|--------|-------|
| Mobile framework (React Native / Flutter) | HIGH | LARGE | No mobile code exists |
| Push notification service | HIGH | MEDIUM | Notification service exists but no push |
| Biometric auth | HIGH | MEDIUM | 2FA service exists, need biometric bridge |
| Offline support | MEDIUM | LARGE | Not applicable to current API design |
| Deep linking | LOW | SMALL | — |
| App store deployment | LOW | MEDIUM | CI/CD pipeline needed |

## Recommendations

1. **Short-term (P1)**: Build internal compliance dashboard (Metabase/Superset per ROADMAP)
2. **Medium-term (P2)**: React/Next.js customer-facing web app
3. **Long-term (P3)**: Mobile app with shared API layer

The FastAPI backend with 42 endpoints provides a solid foundation. The main gaps are all frontend — the API layer is production-ready.

---
*Last updated: 2026-04-10 (Phase 4 migration)*
