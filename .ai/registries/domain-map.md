# Domain Map — banxe-emi-stack
# Source: services/ full scan (FUNCTION 1 — Architecture Skill Orchestrator)
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14: +2619 tests, 87% coverage, stub inventory)
# Purpose: Domain boundaries, trust zones, service ownership, data flows

## Domain overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          BANXE EMI DOMAIN MAP                               │
├───────────────────┬───────────────────────┬─────────────────────────────────┤
│  BANKING CORE     │  COMPLIANCE / RED ZONE│  INFRASTRUCTURE                 │
│  (GREEN zone)     │  (highest sensitivity)│  (BLUE zone)                    │
├───────────────────┼───────────────────────┼─────────────────────────────────┤
│ ledger/       STUB│ aml/          ACTIVE  │ auth/          ACTIVE           │
│ payment/    ACTIVE│ fraud/     ACT+STUB   │ config/        ACTIVE           │
│ customer/   ACTIVE│ kyc/       ACT+STUB   │ events/        ACTIVE           │
│ agreement/ ACT+STUB│ case_mgmt/ ACT+STUB   │ iam/        ACT+STUB            │
│ statements/ ACTIVE│ consumer_duty/ACTIVE  │ notifications/ ACTIVE           │
│ recon/      ACTIVE│ complaints/   ACTIVE  │ providers/     ACTIVE           │
│ reporting/  ACTIVE│ resolution/   ACTIVE  │ webhooks/      ACTIVE           │
│                   │ hitl/         ACTIVE  │                                 │
└───────────────────┴───────────────────────┴─────────────────────────────────┘
```

## Domains

### Banking Core (GREEN trust zone)

| Service | Files | Purpose | FCA reference | Status |
|---------|-------|---------|---------------|--------|
| `services/ledger/` | 2 | Midaz CBS balance queries | CASS 15.3 | STUB |
| `services/payment/` | 5 | FPS/SEPA/BACS via Modulr | PSR 2017 | ACTIVE+STUB |
| `services/customer/` | 2 | Customer lifecycle CRUD | GDPR Art.5 | ACTIVE |
| `services/agreement/` | 1 | Agreement/contract lifecycle + KYC gate (FCA COBS 6) | FCA COBS 6 | ACTIVE+STUB |
| `services/statements/` | 2 | Account statement generation | FCA PS7/24 | ACTIVE |
| `services/recon/` | 10 | CASS 7.15 daily safeguarding recon | CASS 7.15 | ACTIVE+STUB |
| `services/reporting/` | 3 | FIN060 PDF + RegData submission | CASS 15.12.4R | ACTIVE+STUB |

### Compliance (RED trust zone — highest sensitivity)

| Service | Files | Purpose | FCA reference | Status |
|---------|-------|---------|---------------|--------|
| `services/aml/` | 4 | SAR filing, tx monitoring, velocity tracking | MLR 2017 / POCA 2002 s.330 | ACTIVE |
| `services/fraud/` | 5 | FraudAML pipeline, Jube + Sardine adapters | PSR APP 2024 / MLR 2017 Reg.26 | ACTIVE+STUB |
| `services/kyc/` | 3 | KYC workflow, Balleryne EDD | MLR 2017 §18 | ACTIVE+STUB |
| `services/case_management/` | 4 | Marble case routing + case factory; update/close/list added | EU AI Act Art.14 | ACTIVE+STUB |
| `services/consumer_duty/` | 2 | PS22/9 fair value + vulnerability assessment | PS22/9 | ACTIVE |
| `services/complaints/` | 2 | Consumer complaints + n8n webhook | FCA DISP rules | ACTIVE |
| `services/resolution/` | 1 | Resolution pack generation | FCA DISP | ACTIVE |
| `services/hitl/` | 4 | HITL review queue, org roles, SLA tracking | EU AI Act Art.14 | ACTIVE |

### Infrastructure (BLUE zone)

| Service | Files | Purpose | Status |
|---------|-------|---------|--------|
| `services/auth/` | 1 | 2FA service | ACTIVE |
| `services/config/` | 2 | YAML + PostgreSQL config store | ACTIVE |
| `services/events/` | 1 | RabbitMQ pub/sub event bus | ACTIVE |
| `services/iam/` | 2 | Keycloak IAM adapter — JWKS offline RS256 validation (S13-02) | ACTIVE+STUB |
| `services/notifications/` | 4 | Email (SendGrid) + mock | ACTIVE |
| `services/providers/` | 1 | Adapter factory (ProviderRegistry) | ACTIVE |
| `services/webhooks/` | 1 | Inbound webhook router | ACTIVE |

## Data flows

### Flow 1: Transaction Monitoring (real-time)
```
Transaction Event (RabbitMQ)
  → JubeAdapter (ML scoring, gmktec:5001)
  → FraudAMLPipeline.assess()
      ├── FraudScoringPort.score() → FraudRisk (APPROVE/HOLD/BLOCK)
      └── TxMonitorService.evaluate() → MonitorResult
  → HITLService.enqueue() (if requires_hitl=True)
  → SARService.file_sar() (if aml_sar_required=True, MLRO gate)
  → NotificationService (MLRO alert via SendGrid/n8n)
```

### Flow 2: Customer Onboarding
```
POST /v1/customers
  → CustomerManagementPort.create_customer()
  → POST /v1/kyc/workflows
  → KYCWorkflowPort.create_workflow()
  → (if EDD) OrgRoleChecker.check() → MLRO gate
  → SanctionsCheckAgent (Watchman webhook)
  → CDD risk scoring → LifecycleState transition
```

### Flow 3: SAR Filing (POCA 2002)
```
SARService.file_sar() [MLRO gate mandatory]
  → OrgRoleChecker.check(role=MLRO)
  → HITLService.enqueue() with reason=SAR_FILING
  → [Human MLRO decision within 24h SLA]
  → SARService.approve_sar() → SARService.submit_sar()
  → NCA SAROnline (STUB — not yet implemented)
  → AuditLog (ClickHouse, 5-year retention)
```

### Flow 4: CASS 7.15 Daily Reconciliation
```
Cron (daily 06:00 UTC)
  → StatementPoller → mock-ASPSP (CAMT.053)
  → BankStatementParser (XML → transactions)
  → ReconciliationEngine.reconcile()
  → BreachDetector → n8n webhook (if breach)
  → ClickHouseClient (audit trail)
  → POST /v1/reporting/fin060/generate → WeasyPrint PDF
```

### Flow 5: FIN060 Regulatory Submission
```
POST /v1/reporting/fin060/generate
  → FIN060Generator.generate() → WeasyPrint PDF
  → POST /v1/reporting/fin060/submit
  → RegDataReturnService.run_monthly_return()
  → StubRegDataClient (STUB — real FCA submission pending)
```

## HITL gate map

| Decision | HITL required | Role | SLA |
|----------|--------------|------|-----|
| SAR filing | YES — mandatory | MLRO | 24h |
| EDD onboarding | YES — mandatory | MLRO | 4h |
| Sanctions reversal | YES — mandatory | CEO | 1h |
| PEP onboarding | YES — mandatory | MLRO | 4h |
| Account closure | YES — mandatory | MLRO | 4h |
| SAR withdrawal | YES — mandatory | MLRO | 4h |
| Fraud BLOCK decision | YES — conditional | MLRO | 4h |
| Payment >£50k | YES — conditional | CFO | 8h |

## Trust boundaries

- **Compliance ↔ Banking Core:** All data passing from Compliance to Banking Core must go through HITLService.enqueue() for L2+ decisions
- **External Adapters → Internal:** All inbound webhooks (Watchman, Modulr, n8n) validated via HMAC/secret token before processing
- **Agents → Services:** Compliance agents use tool-calling pattern — cannot directly mutate state, only call service methods
- **RAG Service:** No auth currently (local only, port 8765); not exposed externally

---

*Last updated: 2026-04-10 (FUNCTION 1 scan — post-Phase 6)*
