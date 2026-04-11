# Runbooks — BANXE AI Bank

This directory contains operational runbooks for BANXE AI Bank EMI stack.

## Existing Runbooks

| Runbook | Location | Description |
|---------|----------|-------------|
| General Runbook | [`docs/RUNBOOK.md`](../RUNBOOK.md) | Main operational procedures |
| Onboarding | [`docs/ONBOARDING.md`](../ONBOARDING.md) | Developer onboarding |

## P0 Operational Procedures

| Procedure | Script | Schedule |
|-----------|--------|----------|
| Daily safeguarding recon | `scripts/daily-recon.sh` | Daily (CASS 7.15) |
| Monthly FCA return | `scripts/monthly-fca-return.sh` | Monthly |
| Annual audit export | `scripts/audit-export.sh` | Annual |
| Quality gate | `scripts/quality-gate.sh` | Pre-commit / CI |

## Incident Response

For incident response, see:
- [`.claude/commands/incident-analysis.md`](../../.claude/commands/incident-analysis.md)
- [`.claude/specs/incident-template.md`](../../.claude/specs/incident-template.md)

## Adding Runbooks

Each runbook must cover:
1. Trigger / when to run
2. Pre-conditions (what must be true before starting)
3. Step-by-step procedure (numbered, exact commands)
4. Verification (how to confirm success)
5. Rollback (how to undo)
6. Escalation (who to call if it fails)
