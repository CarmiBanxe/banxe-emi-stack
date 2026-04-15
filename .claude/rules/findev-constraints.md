---
paths: ["services/aml/**", "services/kyc/**", "services/recon/**", "services/reporting/**"]
---

# FinDev Agent Constraints — BANXE EMI STACK

## Hard Constraints (НЕЛЬЗЯ нарушать — Section 0)

1. НИКОГДА float для денег — только `Decimal` (Python) / `Decimal(20,8)` (SQL)
2. НИКОГДА секреты в коде — только `.env` / переменные окружения
3. НИКОГДА технологии из санкционных юрисдикций (РФ, Иран, КНДР, Беларусь, Сирия)
4. ВСЕГДА audit trail — каждое финансовое действие логируется в ClickHouse / pgAudit
5. НИКОГДА платные SaaS без self-hosted альтернативы в production

## Priority Matrix (CASS 15 deadline 7 May 2026)

```
P0 (до 7 May):
  1. pgAudit на всех PostgreSQL БД
  2. Daily safeguarding reconciliation (Blnk / bankstatementparser + Midaz)
  3. FIN060 generation → RegData
  4. Frankfurter FX rates (self-hosted ECB)
  5. adorsys PSD2 gateway (bank statement polling)

P1 (Q2-Q3 2026): Metabase/Superset, Great Expectations, Debezium, Temporal, Kafka
P2 (Q4 2026): Camunda 7, OpenMetadata, Airbyte
P3 (Year 2+): FinGPT, OpenBB, Apache Flink
```

## Scope

- **IN scope:** CASS 15 P0 items until 7 May 2026
- **OUT of scope:** AML, KYC, Cards, K8s, full event streaming

## Cross-references

- Full invariants: `financial-invariants.md`
- Security rules: `security-policy.md`
- Compliance boundaries: `compliance-boundaries.md`
- Architecture repo: https://github.com/CarmiBanxe/banxe-architecture
