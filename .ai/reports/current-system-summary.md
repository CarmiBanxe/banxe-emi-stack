# Current System Summary — banxe-emi-stack
# Source: Phase 0 discovery + CLAUDE.md + ROADMAP.md
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: System architecture overview

## System identity

**Banxe AI Bank** — FCA-authorised Electronic Money Institution (EMI)
- Repo: `CarmiBanxe/banxe-emi-stack`
- Regulation: FCA CASS 15 / PS25/12
- Hard deadline: 7 May 2026 (safeguarding compliance)
- Architecture: Python monorepo, FastAPI REST API, microservices pattern

## Architecture stack

```
┌─────────────────────────────────────────────────────────────┐
│                    CLIENT LAYER (future)                      │
│                    Web App / Mobile App                       │
├─────────────────────────────────────────────────────────────┤
│                    API LAYER                                  │
│            FastAPI (42 endpoints, Keycloak OIDC)             │
├──────────────┬──────────────┬───────────────────────────────┤
│ BANKING CORE │ COMPLIANCE   │ INFRASTRUCTURE                 │
│ ledger       │ aml          │ auth, config, events           │
│ payment      │ fraud        │ iam, notifications             │
│ customer     │ kyc          │ providers, webhooks            │
│ agreement    │ case_mgmt    │                                │
│ statements   │ consumer_duty│                                │
│ recon        │ complaints   │                                │
│ reporting    │ resolution   │                                │
│              │ hitl         │                                │
├──────────────┴──────────────┴───────────────────────────────┤
│                 AI COMPLIANCE SWARM                           │
│    7 agents: MLRO, Jube, Sanctions, AML, TM, CDD, Fraud    │
│    ChromaDB KB | PostgreSQL memory | ClickHouse audit        │
├─────────────────────────────────────────────────────────────┤
│                 DATA & PERSISTENCE                           │
│   PostgreSQL 17  │  ClickHouse  │  Redis  │  RabbitMQ       │
│   (OLTP, pgAudit)│  (audit, 5yr)│ (cache) │  (events)       │
├─────────────────────────────────────────────────────────────┤
│                 EXTERNAL INTEGRATIONS                        │
│   Midaz CBS │ Modulr (🔒) │ Frankfurter FX │ adorsys PSD2  │
│   Jube      │ Marble      │ Ballerine      │ Keycloak      │
└─────────────────────────────────────────────────────────────┘
```

## Production infrastructure (GMKtec server)

| Service | Port | Status |
|---------|------|--------|
| Midaz Ledger (CBS) | :8095 | ✅ |
| Keycloak (IAM) | :8180 | ✅ |
| Redis | :6379 | ✅ |
| RabbitMQ | :3004 | ✅ |
| Jube (fraud rules) | :5001 | ✅ |
| Marble (case mgmt) | :5002/:5003 | ✅ |
| Ballerine (KYC) | :3000/:5137 | ✅ |
| n8n (workflows) | :5678 | ✅ |
| Mock ASPSP (PSD2) | :8888 | ✅ |
| PostgreSQL 17 | :5432 | ✅ |
| ClickHouse | :9000 | ✅ |

## Key metrics (2026-04-10)

| Metric | Value |
|--------|-------|
| Total files | 249 |
| Service modules | 22 |
| API endpoints | 42 |
| Test files | 46 |
| Total tests | 995 |
| Coverage | ≥80% |
| AI agents | 9 (2 Claude Code + 7 compliance swarm) |
| Semgrep rules | 10 custom |
| Docker services | 11 running on GMKtec |

## Invariants (enforced)

| # | Rule | Enforcement |
|---|------|-------------|
| I-01 | No float for money | Decimal-only (Python + SQL) |
| I-02 | Hard-block jurisdictions | RU/BY/IR/KP/CU/MM/AF/VE |
| I-03 | FATF greylist → EDD | 23 countries |
| I-04 | EDD threshold £10k | Pipeline + HITL |
| I-08 | ClickHouse 5yr TTL | Schema enforcement |
| I-24 | Audit append-only | Semgrep rule blocks DELETE/UPDATE |
| I-27 | HITL supervised | AI PROPOSES only |
| I-28 | Execution discipline | QRAA + IL ledger |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
