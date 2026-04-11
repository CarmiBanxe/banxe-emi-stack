# Claude Memory Policy — BANXE AI Bank
# IL-SK-01 | Created: 2026-04-11

## What Memory Is For

Claude's memory should capture **learned patterns** that improve future sessions:
how the team works, what conventions are in use, what sequences are reliable.

## Good Uses of Memory

- **Task format patterns**: how tickets are structured, what fields are always present
- **Test sequences**: which test suites to run in what order for a given domain
- **Naming conventions**: file naming, function naming, commit message format
- **Review structure**: what reviewers focus on in this codebase
- **Tool sequences**: what tools to run after what operations (e.g., always scan after edit)

## What Must NOT Live Only in Memory

These items require authoritative storage in the repo, not only in Claude's memory.
Memory can point to them; it cannot replace them.

| Item | Where it lives |
|------|---------------|
| Regulatory requirements | `docs/compliance/`, `banxe-architecture/COMPLIANCE-MATRIX.md` |
| Ledger invariants | `.claude/rules/financial-invariants.md` |
| Sanctions rules | `services/aml/aml_thresholds.py` |
| Secrets | `.env` (never in repo), secrets manager |
| Production procedures | `docs/runbooks/` |
| Agent authority / HITL gates | `.claude/rules/agent-authority.md` |
| Quality gates | `.github/workflows/quality-gate.yml` |

## Memory Freshness

Memory can become stale. Before acting on a recalled memory:
- Check the actual file still exists
- Check the function/field still exists (grep for it)
- If memory conflicts with current code, trust the code — and update the memory

## Memory Index

This directory stores session memory files. Each file follows the format:

```markdown
---
name: Memory name
description: One-line description
type: user | feedback | project | reference
---

Content...
```
