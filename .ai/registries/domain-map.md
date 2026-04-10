# Domain Map — banxe-emi-stack
# Source: services/ analysis, agents/compliance/, config/banxe_config.yaml
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Domain boundaries, trust zones, and service ownership

## Domain overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     BANXE EMI DOMAIN MAP                            │
├───────────────┬─────────────────┬───────────────────────────────────┤
│ BANKING CORE  │ COMPLIANCE      │ INFRASTRUCTURE                    │
│ (GREEN zone)  │ (RED zone)      │ (BLUE zone)                       │
├───────────────┼─────────────────┼───────────────────────────────────┤
│ ledger/       │ aml/            │ auth/                             │
│ payment/      │ fraud/          │ config/                           │
│ customer/     │ kyc/            │ events/                           │
│ agreement/    │ case_management/│ iam/                              │
│ statements/   │ consumer_duty/  │ notifications/                    │
│ recon/        │ complaints/     │ providers/                        │
│ reporting/    │ resolution/     │ webhooks/                         │
│               │ hitl/           │                                   │
└───────────────┴─────────────────┴───────────────────────────────────┘
```

## Domains

### Banking Core (GREEN trust zone)

| Service | Files | Purpose | FCA reference |
|---------|-------|---------|---------------|
| `services/ledger/` | 3 | Midaz CBS client — balance queries, tx creation | CASS 15.3 |
| `services/payment/` | 7 | Payment rails — FPS, SEPA, BACS via Modulr | PSR 2017 |
| `services/customer/` | 3 | Customer lifecycle CRUD | GDPR Art.5 |
| `services/agreement/` | 3 | Agreement/contract lifecycle | — |
| `services/statements/` | 2 | Account statement generation | FCA PS7/24 |
| `services/recon/` | 10 | Daily safeguarding reconciliation | CASS 7.15 |
| `services/reporting/` | 3 | FIN060 PDF, RegData returns | CASS 15.12 |

### Compliance (RED trust zone — highest sensitivity)

| Service | Files | Purpose | FCA reference |
|---------|-------|---------|---------------|
| `services/aml/` | 5 | AML thresholds, SAR service, tx monitoring, velocity | MLR 2017 |
| `services/fraud/` | 6 | FraudAML pipeline, Jube + Sardine adapters | MLR 2017 Reg.26 |
| `services/kyc/` | 3 | KYC workflow, Ballerine adapter | MLR 2017 §18 |
| `services/case_management/` | 5 | Marble adapter, case factory | EU AI Act Art.14 |
| `services/consumer_duty/` | 3 | Consumer duty assessment (PS22/9) | PS22/9 |
| `services/complaints/` | 3 | Consumer complaints + n8n webhook | DISP rules |
| `services/resolution/` | 2 | Resolution pack generation | — |
| `services/hitl/` | 5 | Human-in-the-loop feedback, PROPOSES only | EU AI Act Art.14 |
| `agents/compliance/` | 10 | AI compliance swarm (7 soul agents, 2 workflows) | MLR 2017, JMLSG |

### Infrastructure (BLUE trust zone)

| Service | Files | Purpose |
|---------|-------|---------|
| `services/auth/` | 2 | Two-factor authentication |
| `services/config/` | 4 | YAML config store (config-as-data, IL-040) |
| `services/events/` | 2 | RabbitMQ event bus |
| `services/iam/` | 3 | Keycloak IAM adapter (7 roles) |
| `services/notifications/` | 5 | Email (SendGrid), SMS (Twilio), Telegram |
| `services/providers/` | 2 | Provider registry (plugin architecture) |
| `services/webhooks/` | 2 | Webhook routing |

## Trust zone boundaries

| Zone | Sensitivity | Access control | Audit requirement |
|------|-------------|---------------|-------------------|
| RED | Highest — compliance data, SAR, PEP | MLRO, Compliance Officer | Full ClickHouse audit trail, 5yr retention |
| GREEN | High — financial transactions, balances | Ops staff + API | pgAudit + ClickHouse, DECIMAL only |
| BLUE | Medium — infrastructure, config | Developers + Ops | Standard logging |

## Cross-domain dependencies

| From → To | Interface | Notes |
|-----------|-----------|-------|
| recon/ → ledger/ | MidazLedgerAdapter | Balance queries via LedgerPort (I-28) |
| fraud/ → case_management/ | MarbleAdapter | Alert → case escalation |
| aml/ → hitl/ | HITLService | SAR candidate → MLRO review |
| payment/ → recon/ | ClickHouse safeguarding_events | Payment audit trail feeds reconciliation |
| reporting/ → recon/ | ClickHouse SELECT | FIN060 reads from safeguarding data |
| complaints/ → notifications/ | n8n webhook | Complaint → Telegram MLRO alert |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
