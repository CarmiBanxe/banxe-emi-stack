---
name: migration-check
description: Validate database migration safety before applying
context: fork
agent: Analyze
allowed-tools: Bash(git *), Bash(psql *), Bash(find *), Bash(cat *)
---

## Migration Context

- Pending migrations: `!find . -name "*.py" -path "*/alembic/versions/*" -newer .last_migration 2>/dev/null | sort || find . -name "*.py" -path "*/alembic/versions/*" 2>/dev/null | tail -5`
- Current DB version: `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT version_num FROM alembic_version" 2>/dev/null || echo "DB not available"`
- Migration diff: `!git diff HEAD~3 -- migrations/ alembic/versions/ 2>/dev/null | head -100`
- dbt models: `!find models/ -name "*.sql" 2>/dev/null | wc -l`
- Large tables (row count): `!psql postgresql://banxe:banxe2025@localhost/banxe_db -c "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY n_live_tup DESC LIMIT 10" 2>/dev/null || echo "DB not available"`
- ClickHouse tables: `!find . -name "*.sql" -path "*clickhouse*" 2>/dev/null | wc -l`

## Your task

Analyze the pending migrations for safety:

1. **Reversibility** — does every `upgrade()` have a matching `downgrade()`? Flag irreversible operations (DROP COLUMN, DROP TABLE).
2. **Table locks** — identify `ALTER TABLE` on large tables (>100k rows) that could cause downtime. Recommend `ADD COLUMN ... DEFAULT NULL` or background migration pattern.
3. **Missing indexes** — flag foreign keys in new tables without corresponding indexes.
4. **Data loss risk** — identify `NOT NULL` constraints added to existing columns without a backfill, or column type narrowing.
5. **ClickHouse alignment** — if alembic migration touches audit/event tables, verify ClickHouse schema stays in sync.
6. **dbt impact** — check if new/renamed columns break existing dbt models.

Output a **SAFE / RISKY / BLOCKED** verdict with per-migration breakdown.
BLOCKED = any data loss risk or irreversible operation on a table with >10k rows.
