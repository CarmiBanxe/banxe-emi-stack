# /incident-analysis — Incident Analysis Command
# BANXE AI BANK | IL-SK-01
# Usage: /incident-analysis <description-or-alert-name>

## Protocol

**Do not patch immediately. Investigate first.**

A mis-aimed patch during an incident:
- Masks the root cause
- Complicates the audit trail
- Can trigger a second, worse incident

Investigation always precedes mitigation.

## Analysis Output Format

Produce the following sections in order:

### 1. Fault Domain
Which system is confirmed affected (not suspected — only what evidence shows).

### 2. Symptoms
Observed behaviour: error messages, latency spikes, alert names, affected endpoints.
Use exact quotes from logs/alerts where possible.

### 3. Facts
What is definitively known. Source each fact: log line, metric, DB query result.

### 4. Unknowns
What we do not yet know. What questions must be answered before a fix is safe.

### 5. Evidence
Exact log lines, metric values, stack traces. Do not paraphrase — quote directly.

### 6. Mitigation
Immediate action to limit harm. NOT a fix. Options: circuit breaker, feature flag,
rollback, rate limit, manual override.

### 7. Hypotheses
Ranked list of root cause hypotheses. For each: what evidence supports it, what would
refute it, what would confirm it.

### 8. Next Action
Single most important investigative step in the next 15 minutes.

## What Requires Human Approval Before Acting

- Deleting or truncating any table
- Schema changes on live financial tables
- Mass reprocessing or event replay
- Secret rotation
- Any action that cannot be undone

## Template

Use `.claude/specs/incident-template.md` for formal incident records.
