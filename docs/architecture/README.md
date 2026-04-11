# Architecture Documentation — BANXE AI Bank

This directory contains architecture documentation for BANXE AI Bank EMI stack.

## Contents

| File | Description |
|------|-------------|
| _(add ADR files here)_ | Architecture Decision Records |

## Key Architecture References

- **Overview**: [`docs/ARCHITECTURE-RECON.md`](../ARCHITECTURE-RECON.md) — reconciliation architecture
- **Component map**: [`banxe-architecture`](https://github.com/CarmiBanxe/banxe-architecture) — canonical architecture repo
- **Domain boundaries**: [`.claude/rules/compliance-boundaries.md`](../../.claude/rules/compliance-boundaries.md)
- **Agent registry**: [`.ai/registries/`](../../.ai/registries/)

## P0 Stack

```
Midaz (ledger) → Blnk + bankstatementparser (recon) → dbt → FIN060 (reporting)
PostgreSQL (pgAudit) + ClickHouse (5yr TTL audit) + Redis
n8n (workflows) | Grafana (monitoring) | Semgrep (SAST)
```

## Adding Architecture Docs

1. Create a new `.md` file in this directory
2. Update this README with a table entry
3. For architectural decisions: use `docs/adr/` with ADR format
