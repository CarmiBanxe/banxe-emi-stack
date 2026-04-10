# prompts/ — Workflow Prompts
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Store workflow prompts used in this migration and ongoing operations

## Migration prompts (Google Drive originals)

These prompts drive the Claude AI scaffold migration. Originals are stored in
Google Drive (CarmiBanxe account). Local copies are placed here for reference.

| File | Google Drive ID | Purpose |
|------|----------------|---------|
| `00-MASTER-INSTRUCTIONS.md` | `1M3ybxN0bBou_3KA5kThkB3cspskH08PE` | Master workflow (3 prompts: safety → refactoring → orchestrator) |
| `01-safety-orchestration.md` | `11AnSBQU2v41xMsdWntU9bX9mw7eceF2U` | Safety framework (7 agents, checkpoint/rollback/batching) |
| `02-main-refactoring.md` | `1JJCNTVK4tUCtVWkoMCqCc4wlRxBWw5_p` | Main refactoring (11 phases: 0-10) |
| `03-architecture-skill-orchestrator.md` | `1Gru_DtCyrhJu9PE8Vl-Vhc1sK2ug9Xs2` | Post-refactoring skill orchestrator (NOT YET READ) |

## Usage

These prompts are designed to be fed sequentially to Claude Code:
1. Read `00-MASTER-INSTRUCTIONS.md` first (sets execution context)
2. Execute `01-safety-orchestration.md` (establishes safety framework)
3. Execute `02-main-refactoring.md` (11-phase migration)
4. Load `03-architecture-skill-orchestrator.md` (post-migration skill)

## Note

Full prompt content is stored in Google Drive, not duplicated here, to maintain
a single source of truth. Download via Google Drive IDs above if needed locally.
