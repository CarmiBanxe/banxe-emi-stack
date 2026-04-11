# Documentation Rules — BANXE AI BANK
# Rule ID: 40-docs | Load order: 40
# Created: 2026-04-11 | IL-SK-01

## When Documentation Must Be Updated

Documentation is a deliverable, not an afterthought. Update docs when changing:

| Change type | Required doc update |
|-------------|---------------------|
| API behaviour or fields | `docs/API.md` + OpenAPI schema |
| Architecture components | `docs/architecture/` |
| Compliance controls | `docs/compliance/` |
| Runbook / operational procedure | `docs/runbooks/` |
| Schema or migration | Migration spec + `docs/architecture/` |
| Config / environment variable | `.env.example` + runbook |
| New ADR decision | `docs/adr/` (new file) |

## Documentation Targets

- `docs/architecture/` — system design, component boundaries, data flow diagrams
- `docs/compliance/` — control descriptions, regulatory mapping, evidence pointers
- `docs/runbooks/` — operational procedures, incident response, deployment steps
- `docs/adr/` — Architecture Decision Records (ADR) for significant decisions

## Writing Style

Every documentation change must cover:

1. **What changed** — specific behaviour, field, schema, or procedure
2. **Why** — business or regulatory reason
3. **Risks** — what could go wrong if the doc is wrong or stale
4. **Rollback** — how to revert if the change causes problems

## ADR Format

New ADRs must include: title, date, status (proposed/accepted/deprecated), context,
decision, consequences, and alternatives considered.

## Stale Doc Policy

- Doc update is part of the PR, not a follow-up task.
- "Docs deferred" requires explicit ticket and IL entry.
- Stale compliance docs are a regulatory risk: treat as P1.
