# Skills Directory

Claude Code skills for the BANXE EMI Stack project.

## Format Convention

Two valid skill formats coexist by design:

| Format | When to Use | Example |
|--------|------------|--------|
| **Flat file** `skill-name.md` | Simple skills with no reference data | `aml-review.md`, `kyc-debug.md` |
| **Subfolder** `skill-name/SKILL.md` | Skills with reference docs, configs, or datasets | `lucidshark/`, `supabase-postgres-best-practices/` |

## Current Skills (11)

### Flat Skills
| Skill | Agent | Purpose |
|-------|-------|---------|
| aml-review | Explore | AML alert triage and monitoring |
| banxe-health | - | Project health snapshot |
| compliance-check | Analyze | FCA/EU compliance posture |
| cross-repo-sync | Explore | Sync status across 13 repos |
| kyc-debug | Explore | KYC pipeline diagnostics |
| migration-check | Analyze | Database migration safety |
| ollama-model-health | Explore | Ollama model crash detection |
| pr-review | Analyze | Code review with BANXE focus |
| telegram-bot-debug | Explore | Telegram bot diagnostics |

### Subfolder Skills
| Skill | Purpose |
|-------|---------|
| lucidshark | Unified code quality and security scanner |
| supabase-postgres-best-practices | Postgres optimization guide (v1.1.1) |
