# Financial Invariants — BANXE AI BANK
# Source: CLAUDE.md §0 (Hard Constraints), ROADMAP.md (Invariants table)
# Created: 2026-04-10
# Migration Phase: 3
# Purpose: Machine-enforceable financial rules for all code changes

## Hard Financial Rules

- NEVER use `float` for money — only `Decimal` (Python) / `Decimal(20,8)` (SQL)
- NEVER expose secrets in code — only `.env` / environment variables
- ALWAYS log every financial action to ClickHouse / pgAudit (append-only)
- NEVER use paid SaaS without a self-hosted alternative in production
- NEVER use technologies from sanctioned jurisdictions (RU, IR, KP, BY, SY)

## Invariant Registry

| ID | Rule | Enforcement |
|----|------|-------------|
| I-01 | No float for money | Semgrep `banxe-float-money`, Ruff |
| I-02 | Hard-block jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE | `services/aml/aml_thresholds.py` |
| I-03 | FATF greylist → EDD (23 countries) | `services/aml/aml_thresholds.py` |
| I-04 | EDD threshold £10k (individual), £50k (corporate) | `services/aml/aml_thresholds.py` |
| I-05 | Decimal strings in API responses | Pydantic validators in `api/models/` |
| I-08 | ClickHouse TTL ≥ 5 years | Semgrep `banxe-clickhouse-ttl-reduce` |
| I-24 | AuditPort is append-only (no UPDATE/DELETE) | Semgrep `banxe-audit-delete` |
| I-27 | HITL feedback is supervised (PROPOSES only, never auto-applies) | `services/hitl/feedback_loop.py` |
| I-28 | Execution discipline: QRAA + IL ledger | CLAUDE.md session protocol |

## References

- Semgrep rules: `.semgrep/banxe-rules.yml`
- AML thresholds: `services/aml/aml_thresholds.py`
- Full invariant list: `ROADMAP.md` § Invariants
