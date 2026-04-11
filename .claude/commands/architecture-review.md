# /architecture-review — Architecture Review Command
# BANXE AI BANK | IL-SK-01
# Usage: /architecture-review <component-or-change>

## Review Against Banxe Architecture Boundaries

This review validates a component or change against the established Banxe domain boundaries
(defined in `.claude/rules/compliance-boundaries.md` and `banxe-architecture` repo).

## Output Format

### 1. Components Involved
List every service, module, DB, queue, and external dependency touched by this change.

### 2. Coupling Analysis
- New dependencies introduced (service → service, service → DB, service → external)
- Bidirectional dependencies (potential circular coupling)
- Cross-domain calls (e.g., AML calling Ledger directly — is this allowed?)

### 3. Data Flow
Trace the data path end-to-end:
`Input source → processing steps → storage → downstream consumers`

Mark where financial amounts are transformed, where PII is handled, where audit events are emitted.

### 4. Failure Modes
For each new integration point: what happens if it fails?
- Timeout / unavailable: fallback behaviour?
- Partial failure: is the system left in a consistent state?
- Data loss scenario: is there a recovery path?

### 5. Operational Impact
- Observability: is this component visible in Grafana dashboards?
- Alerting: are alerts defined for failure states?
- On-call: does the runbook cover this component?

### 6. Security and Compliance
- Trust zone: which zone does this component operate in? (see `compliance-boundaries.md`)
- Data classification: does it handle PII, financial data, or secrets?
- Audit trail: does every state change produce an audit event?

### 7. ADR Needed?
If this decision is significant and not yet documented:
> "This change requires an ADR. Suggested title: [X]"

Significant = affects domain boundaries, introduces new external dependency, changes
data ownership, or alters a compliance control.
