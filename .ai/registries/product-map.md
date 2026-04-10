# Product Map — banxe-emi-stack
# Source: ROADMAP.md, CLAUDE.md (P0/P1/P2/P3), config/banxe_config.yaml
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Product features, phases, completion status

## Product overview

**Banxe AI Bank** — FCA-authorised Electronic Money Institution (EMI)
- Primary regulation: FCA CASS 15 / PS25/12
- Hard deadline: 7 May 2026 (safeguarding compliance)
- Product types: EMI Account, Business Account, FX Account, Prepaid Card

## Phase completion

| Phase | Name | Status | Tests | Key deliverable |
|-------|------|--------|-------|-----------------|
| Phase 1 | Core EMI Platform | ✅ COMPLETE | 867 | 13 features: safeguarding, recon, payments, KYC, AML, IAM, API |
| Phase 2 | Operations & Compliance Intelligence | 🔄 IN PROGRESS | — | HITL, notifications, Jube, Marble, Ballerine; 4 items BLOCKED |
| Phase 3 | Advanced Compliance Reporting | ✅ COMPLETE | — | FIN060 API, SAR auto-filing, consumer duty annual report |
| Phase 4 | Infrastructure & Deployment | ✅ DEPLOYED | — | GMKtec deploy, systemd timer, n8n workflows, Keycloak |

## P0 items (deadline: 7 May 2026)

| # | Item | IL | Status | FCA ref |
|---|------|-----|--------|---------|
| 1 | pgAudit on all PostgreSQL DBs | IL-009..011 | ✅ | CASS 15.12 |
| 2 | Daily safeguarding reconciliation | IL-012..013 | ✅ | CASS 7.15 |
| 3 | FIN060 generation → RegData | IL-015 | ✅ | CASS 15.12.4R |
| 4 | Frankfurter FX rates (self-hosted ECB) | IL-010 | ✅ | — |
| 5 | adorsys PSD2 gateway (bank statement polling) | IL-011 | ✅ | CASS 7.15 FA-07 |

## Blocked items (external dependencies)

| # | Item | Blocker | Owner | Status |
|---|------|---------|-------|--------|
| BT-001 | Modulr Payments API (live) | CEO: register modulrfinance.com/developer | CEO | 🔒 |
| BT-002 | Companies House KYB | COMPANIES_HOUSE_API_KEY | Ops | 🔒 |
| BT-003 | OpenCorporates KYB | OPENCORPORATES_API_KEY | Ops | 🔒 |
| BT-004 | Sardine.ai Fraud Scoring | SARDINE_API_KEY / SARDINE_CLIENT_ID | Ops | 🔒 |

## Future roadmap

| Priority | Timeline | Items |
|----------|----------|-------|
| P1 | Q2-Q3 2026 | Metabase/Superset, Great Expectations, Debezium, Temporal, Kafka |
| P2 | Q4 2026 | Camunda 7, OpenMetadata, Airbyte |
| P3 | Year 2+ | FinGPT, OpenBB, Apache Flink |

## Products (from config/banxe_config.yaml)

| Product | Currencies | Status | Key fees |
|---------|------------|--------|----------|
| EMI Account | GBP, EUR, USD | Active | FPS £0.20, SEPA CT €0.50, FX 0.25% |
| Business Account | GBP, EUR, USD, CHF | Active | FPS £0.30, SEPA CT €1.00, FX 0.20% |
| FX Account | GBP, EUR, USD, CHF, JPY, CAD, AUD, SGD | Active | FX 0.15% |
| Prepaid Card | GBP, EUR | Active | Card FX 2%, FPS top-up free |

## Transaction limits (Individual)

| Product | Single TX | Daily | Monthly |
|---------|-----------|-------|---------|
| EMI Account | £50,000 | £25,000 | £100,000 |
| Business Account | £100,000 | £50,000 | £200,000 |
| FX Account | £25,000 | £25,000 | £100,000 |
| Prepaid Card | £5,000 | £5,000 | £20,000 |

---
*Last updated: 2026-04-10 (Phase 4 migration)*
