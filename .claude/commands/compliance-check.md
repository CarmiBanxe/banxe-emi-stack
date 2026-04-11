# /compliance-check — Compliance Review Command
# BANXE AI BANK | IL-SK-01
# Usage: /compliance-check <feature-or-change-description>

## Lens

Review the change through a **control and audit lens**, not a feature lens.
The question is not "does this work?" but "does this satisfy the regulatory requirement
and leave an auditable trail?"

## Output Format

### 1. Affected Control
Which FCA/regulatory control does this change touch?
Reference: CASS 15, MLR 2017, PSR 2017, PS22/9 Consumer Duty, PSD2 SCA, EU AI Act Art.14.

### 2. Requirement Source
Exact regulatory reference (e.g., "CASS 15.2.2R — daily safeguarding reconciliation").
If the requirement is not in the repo documentation, state: **UNVERIFIED — not found in repo**.

### 3. Decision Points
Where in the code does a compliance decision happen?
List: file path, function name, what decision is made, what data it uses.

### 4. Evidence Trail
How is this decision logged? ClickHouse table, pgAudit, event bus, report?
Confirm: append-only, TTL ≥ 5 years (I-08), no DELETE possible (I-24).

### 5. Explainability
Can a regulator or auditor follow what happened and why?
Is the decision deterministic and reproducible from stored data?

### 6. Gaps
List any control gaps: missing logging, missing validation, missing human approval gate,
missing documentation.

### 7. Approvals Required
Which roles must approve before this change goes live?
Reference `agent-authority.md` for HITL gates.

## Explicit Unverified Statement

If any requirement cannot be verified in the repo, state:
> "Requirement [X] is UNVERIFIED — it is not confirmed in the current codebase or documentation."

Do not assume compliance. Evidence is required.
