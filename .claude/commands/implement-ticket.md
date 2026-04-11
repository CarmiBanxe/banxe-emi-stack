# /implement-ticket — Ticket Implementation Command
# BANXE AI BANK | IL-SK-01
# Usage: /implement-ticket <ticket-ID>

## Prerequisites

- An approved plan must exist (from `/plan-feature`) before implementation begins.
- No implementation without a plan. If no plan exists, run `/plan-feature` first.

## Implementation Protocol

1. **Use the approved plan only** — do not deviate from the agreed approach without flagging it.
2. **Smallest safe slice** — implement one step at a time; commit after each slice passes tests.
3. **No scope widening** — if you discover adjacent improvements, note them as follow-up tickets.
   Do not fold them into the current implementation.
4. **Stop and ask before destructive actions** — any DROP, DELETE, secret rotation, or
   irreversible schema change requires explicit confirmation before execution.

## Per-Slice Report

After each implementation slice, output:

| Field | Content |
|-------|---------|
| **What changed** | Files modified, functions added/changed, schema changes |
| **Why** | Which requirement or plan step this satisfies |
| **Tests run** | Test names, pass/fail counts |
| **Remaining risks** | Any new risks discovered during implementation |
| **Docs updated** | Which documentation files were updated |

## Quality Gate (required before "done")

- [ ] `ruff check .` — zero issues
- [ ] `ruff format --check .` — passes
- [ ] `semgrep --config .semgrep/banxe-rules.yml --error` — zero violations
- [ ] `pytest tests/ -x -q` — all pass
- [ ] LucidShark scan clean (if code files changed)
- [ ] Infrastructure Checklist items ticked (see `.claude/CLAUDE.md`)

## Definition of Done

A ticket is done when: implementation complete + tests passing + docs updated + quality gates
green + IL entry updated to DONE.
