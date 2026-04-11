# Migration Rules — BANXE AI BANK
# Rule ID: 60-migrations | Load order: 60
# Created: 2026-04-11 | IL-SK-01

## Required Sections in Every Migration Spec

Before writing a migration, produce a spec (use `.claude/specs/migration-spec-template.md`)
with all of the following sections:

| Section | Content |
|---------|---------|
| **Purpose** | What business or compliance need drives this migration |
| **Data affected** | Tables, columns, row counts (estimated), data types |
| **Forward steps** | Exact SQL/commands to apply the migration |
| **Rollback steps** | Exact SQL/commands to reverse it; confirm reversibility |
| **Compatibility** | Is the migration backward-compatible with the current app version? |
| **Validation checks** | Assertions to run after migration to confirm correctness |
| **Blast radius** | What breaks if this migration fails mid-flight |

## Safety Rules

- **Additive changes first**: add nullable column → backfill → add NOT NULL constraint
  (never add a NOT NULL column with no default on a live table in one step).
- **Validate assumptions before running**: check row count, check column existence,
  check index presence before the migration touches data.
- **Call out locking risks**: any ALTER that locks a table must be flagged. Prefer
  `CREATE INDEX CONCURRENTLY`, `ADD COLUMN` with nullable, or `pt-online-schema-change`
  patterns.
- **No data destruction without explicit approval**: DROP TABLE, TRUNCATE, DELETE without
  WHERE require MLRO/CEO sign-off if the table contains financial or audit data.
- **ClickHouse migrations**: use `infra/clickhouse/migrations/` numbered sequence.
  Never reduce TTL below 5 years on audit tables (invariant I-08).
- **PostgreSQL migrations**: use `infra/postgres/migrations/` numbered sequence.
  pgAudit must be active before migrations on financial tables.

## Post-Migration Checklist

- [ ] Validation checks passed
- [ ] No unexpected row count changes
- [ ] Application started cleanly after migration
- [ ] Rollback tested in staging
- [ ] Migration file committed with sequential number
