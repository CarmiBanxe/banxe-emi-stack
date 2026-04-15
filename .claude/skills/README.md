# Skills Directory

Claude Code skills for the BANXE EMI Stack project.

## Token Budget Warning
Each skill loads ~50 tokens at session start. Keep total skills minimal.
Disable skills not needed in current contour.

## Active Skills (Banking Contour)

| Skill | Purpose | Status |
|-------|---------|--------|
| `compliance-check.md` | FCA compliance validation | ✅ ACTIVE |
| `aml-review.md` | AML/KYC review patterns | ✅ ACTIVE |
| `kyc-debug.md` | KYC workflow debugging | ✅ ACTIVE |
| `migration-check.md` | DB migration safety | ✅ ACTIVE |
| `banxe-health.md` | System health monitoring | ✅ ACTIVE |
| `lucidshark/` | Code quality scanning | ✅ ACTIVE |
| `supabase-postgres-best-practices/` | PostgreSQL optimization | ✅ ACTIVE |

## Disabled Skills (not needed in Banking Contour)

| Skill | Reason | How to re-enable |
|-------|--------|------------------|
| `telegram-bot-debug.md` | Standby Plane only | Remove `disable-model-invocation: true` |
| `ollama-model-health.md` | Standby Plane only | Remove `disable-model-invocation: true` |
| `pr-review.md` | Use LucidShark instead | Remove `disable-model-invocation: true` |

## context: fork Skills (heavy operations, run in isolated subprocess)

| Skill | Reason |
|-------|--------|
| `cross-repo-sync.md` | Touches 13 repos, heavy read | 

## Format Convention

Two valid formats coexist:
- **Flat file** `skill-name.md` — Simple skills with no reference data
- **Subfolder** `skill-name/SKILL.md` — Skills with reference docs or datasets
