# Mobile Map — banxe-emi-stack
# Source: api/routers/, config/banxe_config.yaml, ROADMAP.md
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14: SCA screen in banxe-platform/mobile)
# Migration Phase: 5
# Purpose: Mobile app architecture analysis and readiness assessment

## Current state

No mobile application exists. Backend REST API (42 endpoints) provides the foundation.
CORS origins include `localhost:3000` and `localhost:5173` — no mobile-specific config.

## Proposed mobile architecture

### App identity

| Attribute | Value |
|-----------|-------|
| Name | Banxe (customer-facing mobile banking) |
| Target | iOS 16+ / Android 13+ |
| Priority | P3 per ROADMAP.md |
| Depends on | Web portal (P2), live payment rails (BT-001) |

### Recommended stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Framework | React Native (Expo) | Code sharing with web portal, large ecosystem |
| Alternative | Flutter | Higher performance, single codebase, Dart |
| Auth | Keycloak OIDC + biometric | AppAuth library + local biometric unlock |
| State | TanStack Query | Same as web — consistent patterns |
| Navigation | React Navigation 7+ | Standard for RN, deep linking support |
| Push | Firebase Cloud Messaging | Free tier sufficient; backend sends via notification service |
| Secure storage | expo-secure-store / react-native-keychain | Token and biometric key storage |

### Mobile-specific screens

```
Splash / Biometric Unlock
├── Login (Keycloak OIDC AppAuth flow)
├── KYC Onboarding (mandatory first flow)
│   ├── Document Capture (camera + upload)
│   ├── Liveness Check (selfie)
│   └── Verification Status
├── Dashboard
│   ├── Account Balances (multi-currency)
│   ├── Recent Transactions (5 most recent)
│   └── Quick Actions (Send, Request, Top-up)
├── Accounts
│   ├── Account Detail + Balance
│   └── Full Transaction History (paginated)
├── Send Payment
│   ├── Recipient Input (IBAN / sort-code)
│   ├── Amount + Currency
│   ├── Review + Confirm (biometric)
│   └── Payment Status (real-time polling)
├── Notifications
│   ├── Push notification inbox
│   └── Notification detail
├── Profile / Settings
│   ├── Personal details
│   ├── Security (change PIN, biometric toggle)
│   └── Logout
└── Statements (PDF download / share)
```

## Endpoint mapping for mobile

### Core screens

| Screen | API endpoints | Auth | Priority |
|--------|-------------|------|----------|
| Dashboard | GET /v1/ledger/accounts, GET .../balance | CUSTOMER | P1 |
| Send Payment | POST /v1/payments, POST /v1/fraud/assess | CUSTOMER | P1 |
| Payment Status | GET /v1/payments/{key} | CUSTOMER | P1 |
| Transaction History | GET /v1/payments | CUSTOMER | P1 |
| KYC Onboarding | POST /v1/kyc/workflows, POST .../documents | CUSTOMER | P1 |
| KYC Status | GET /v1/kyc/workflows/{id} | CUSTOMER | P1 |
| Profile | GET /v1/customers/{id} | CUSTOMER | P2 |
| Notifications | GET /v1/notifications/{id}/status | CUSTOMER | P2 |
| Statements | (needs new endpoint) | CUSTOMER | P2 |

### Mobile endpoints consumed: 14 of 42

| Category | Endpoints used | Endpoints not used (internal-only) |
|----------|---------------|-----------------------------------|
| Customer | 2 (GET, GET by ID) | 2 (POST create, lifecycle — ops only) |
| Payments | 3 (POST, GET list, GET by key) | 0 |
| Ledger | 2 (GET accounts, GET balance) | 0 |
| KYC | 3 (POST start, POST docs, GET status) | 2 (approve-edd, reject — ops only) |
| Fraud | 1 (POST assess — called server-side) | 0 |
| Notifications | 1 (GET status) | 2 (send, preview — ops only) |
| Health | 2 (liveness, readiness) | 0 |
| **Total mobile** | **14** | **28 (internal/ops)** |

## Backend gaps for mobile

| Gap | Impact | Effort | Priority |
|-----|--------|--------|----------|
| Push notification service | No push — only email/Telegram today | MEDIUM | P1 for mobile |
| Biometric token refresh | Keycloak refresh_token + biometric | MEDIUM | P1 for mobile |
| Device fingerprinting | Sardine.ai blocked (BT-004) | — | Blocked |
| Statement PDF download | No endpoint | SMALL | P2 |
| FX rate display | No endpoint (Frankfurter is internal) | SMALL | P2 |
| Account opening flow | No POST /v1/accounts | MEDIUM | P1 |
| Pagination on list endpoints | No cursor/offset | SMALL | P1 |
| Rate limiting per device | No per-device rate limits | MEDIUM | P2 |
| Offline mode | API-only design, no offline support | LARGE | P3 |
| App-to-app payment links | No deep link schema | SMALL | P3 |

## Security considerations for mobile

| Concern | Mitigation |
|---------|-----------|
| Token storage | expo-secure-store / Keychain, never AsyncStorage |
| Certificate pinning | Required for production (prevent MITM) |
| Root/jailbreak detection | Block API access from compromised devices |
| Biometric auth | Local biometric unlock for token access, not sent to server |
| Screen capture | Disable screenshots on sensitive screens (balance, payment) |
| Transport | TLS 1.3 only, HSTS headers on API |

## Timeline estimate

| Phase | Scope | Duration |
|-------|-------|----------|
| M-01 | Skeleton + auth + dashboard | 4-6 weeks |
| M-02 | Payments + KYC | 4-6 weeks |
| M-03 | Notifications + statements | 2-3 weeks |
| M-04 | Polish + App Store submission | 3-4 weeks |
| **Total** | | **13-19 weeks** |

Pre-requisites: live payment rails (BT-001), web portal (P2 complete), push notification backend.

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*


## EXTRACT Update — 2026-04-13 (FUNCTION 3)

### New mobile integration points (post-safeguarding)

COMPONENT: Safeguarding Breach Push Notification
SOURCE: src/safeguarding/ + services/notifications/
STATUS: ready — backend notification service active, push integration needed
SCREEN TYPE: push notification + modal alert
DATA MODEL: BreachRecord (breach_id, amount, detected_at)
AUTH REQUIRED: yes — internal staff only (MLRO)
COMPLIANCE FLAG: yes — CASS 15
PRIORITY: MVP (P1)
NOTES: Safeguarding breaches must trigger immediate push notifications to MLRO via mobile. Wire Firebase Cloud Messaging to safeguarding breach detector.

COMPONENT: Recon Status Badge
SOURCE: services/settlement/ (tri-party recon, commit cabfb2f)
STATUS: ready — backend done, mobile needs status polling endpoint
SCREEN TYPE: status badge on dashboard
DATA MODEL: ReconciliationStatus (date, status, breach_flag)
AUTH REQUIRED: yes
COMPLIANCE FLAG: yes — CASS 7.15
PRIORITY: P2
NOTES: Can surface recon status as a small compliance indicator on mobile ops dashboard.

*Last updated: 2026-04-13 (FUNCTION 3 EXTRACT — Architecture Skill Orchestrator)*
