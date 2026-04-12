# ADR-002: ClickHouse as Append-Only Financial Audit Log (5-year TTL)

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-010 + IL-013
**Author:** Moriel Carmi / Claude Code

---

## Context

FCA MLR 2017 requires 5-year retention of all financial event records. We need a storage layer for high-throughput financial events that:
1. Cannot be modified or deleted after write (regulatory immutability requirement)
2. Supports compulsory 5-year retention via TTL
3. Handles millions of events/day efficiently (safeguarding, payments, AML)
4. Is self-hosted (FCA data residency — no data leaves UK infrastructure)

PostgreSQL with pgAudit covers schema-level DDL/DML audit but is not designed for high-throughput time-series event ingestion.

---

## Decision

**ClickHouse** (self-hosted, port `:9000`) as the append-only financial audit log.

Key tables:
- `banxe.safeguarding_events` — daily reconciliation events
- `banxe.payment_events` — payment audit trail (TTL 5yr)

---

## Rationale

| Criterion | ClickHouse | PostgreSQL | Elasticsearch |
|-----------|-----------|------------|---------------|
| Write throughput | 100k+ rows/s (column batching) | ~10k rows/s | ~50k docs/s |
| Native TTL | Yes (`TTL event_date + INTERVAL 5 YEAR`) | No (manual partitioning) | Yes (ILM) |
| Append-only by design | MergeTree engine | Requires application enforcement | No |
| Self-hosted | Yes | Yes | Yes |
| SQL interface | Yes (ClickHouse SQL) | Yes | No (KQL) |
| Storage efficiency | 10–50x compression (columnar) | Row-based | Medium |
| FCA data residency | Yes | Yes | Yes |

ClickHouse wins on all financial-audit-specific criteria.

---

## Consequences

### Positive
- TTL is enforced at storage engine level — no application code can circumvent 5-year retention
- MergeTree's append-only semantics enforce I-24 structurally (not just by convention)
- Semgrep rules `banxe-clickhouse-ttl-reduce` and `banxe-audit-delete` enforce invariants I-08 and I-24 at code level

### Negative / Risks
- ClickHouse does not support UPDATE/DELETE (by design) — corrections require compensation events
- Requires ClickHouse infrastructure on GMKtec (port :9000) — additional ops burden
- ClickHouse SQL dialect differs from PostgreSQL — developers must learn both

### Mitigations
- Compensation event pattern documented in `docs/runbooks/`
- ClickHouse `InMemoryReconClient` stub enables full test suite without ClickHouse running
- `banxe-clickhouse-ttl-reduce` Semgrep rule prevents accidental TTL reduction below 5yr

---

## Invariants Enforced

| Invariant | Rule | Enforcement |
|-----------|------|-------------|
| I-08 | ClickHouse TTL ≥ 5 years | Semgrep `banxe-clickhouse-ttl-reduce` (ERROR) |
| I-24 | Audit tables are append-only (no UPDATE/DELETE) | Semgrep `banxe-audit-delete` (ERROR) |

---

## References

- `infra/clickhouse/migrations/` — migration scripts
- `services/recon/clickhouse_client.py` — production client + InMemoryReconClient stub
- `.semgrep/banxe-rules.yml` — rules banxe-clickhouse-ttl-reduce, banxe-audit-delete
- IL-010: pgAudit + ClickHouse schema deployment
