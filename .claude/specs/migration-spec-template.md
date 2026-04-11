# Migration Spec — [TITLE]
# Ticket: [IL-XX-NN]
# Author: | Date: | DB: PostgreSQL / ClickHouse
# Migration file: infra/[db]/migrations/NNN_[name].sql

---

## Reason
_Why is this migration needed? Regulatory, performance, or correctness driver?_

## Data Affected

| Table | Rows (est.) | Change type | Notes |
|-------|-------------|-------------|-------|
| | | ADD COLUMN / DROP COLUMN / ALTER TYPE / CREATE INDEX | |

## Backward Compatibility
_Is the current application version compatible with the post-migration schema?_

- [ ] **Yes** — application continues to work before and after migration
- [ ] **No** — requires coordinated deployment (migration + app release together)
- [ ] **Partial** — explain:

## Forward Steps
_Exact SQL commands in order._

```sql
-- Step 1: 
-- Step 2: 
```

## Rollback Steps
_Exact SQL commands to reverse the migration. Confirm this is tested._

```sql
-- Rollback Step 1: 
```

## Validation Checks
_Assertions to run immediately after migration to confirm correctness._

```sql
-- Check 1: row count unchanged
-- Check 2: new column has expected default
-- Check 3: index exists
```

## Downtime Risk
_Does this migration lock any table? For how long? At what row count?_

- Lock type: SHARE / EXCLUSIVE / NONE
- Estimated lock duration:
- Mitigation: (CONCURRENTLY / batched / pt-osc)

## Monitoring
_What metric or alert will confirm the migration completed successfully?_

## Owner Approvals

| Role | Required | Sign-off |
|------|----------|---------|
| Engineer | ✅ | |
| CTIO (if audit table affected) | | |
| MLRO (if financial data affected) | | |
| CFO (if FIN060 data affected) | | |
