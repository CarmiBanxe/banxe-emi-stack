# Incident Rules — BANXE AI BANK
# Rule ID: 95-incidents | Load order: 95
# Created: 2026-04-11 | IL-SK-01

## Core Principle: Investigate Before Patching

Never apply a fix to a production issue without first understanding the fault domain.
A mis-aimed patch can mask the real cause, complicate the audit trail, and create a
second incident. Investigation comes first.

## First Response Output

When an incident is raised, the first output must be an incident brief covering:

| Section | Content |
|---------|---------|
| **Fault domain** | Which system/service/component is confirmed affected |
| **Impact** | Who is affected, how many, since when, what they cannot do |
| **Timeline** | Chronological sequence of observed events (with timestamps) |
| **Evidence** | Log lines, alert names, dashboard panel, error messages — exact quotes |
| **Mitigation** | Immediate action taken to limit harm (not a fix — a containment) |
| **Next step** | Single most important action to take in the next 15 minutes |

Use `.claude/specs/incident-template.md` for structured output.

## What You Must Never Do Blindly

These actions require explicit human (MLRO/CEO/CTIO) approval during an incident:

- **Destructive cleanup**: deleting records, truncating tables, dropping queues
- **Schema changes**: any ALTER/DROP on live financial tables during an incident
- **Mass reprocessing**: replaying events or rerunning reconciliation without root cause confirmed
- **Secret rotation**: rotating production secrets without co-ordinated deployment

## Post-Incident

- Every P0/P1 incident requires a post-mortem within 5 business days.
- Root cause, contributing factors, and follow-up actions must be logged.
- Follow-up tickets must reference the incident ID in their description.
- If a runbook was missing or wrong: update `docs/runbooks/` as part of the post-mortem.

## References

- Incident template: `.claude/specs/incident-template.md`
- Runbooks: `docs/runbooks/`
- On-call escalation: `.ai/registries/agent-map.md` (HITL gates section)
