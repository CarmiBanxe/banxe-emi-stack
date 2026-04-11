# /plan-feature — Feature Planning Command
# BANXE AI BANK | IL-SK-01
# Usage: /plan-feature <feature-name-or-ticket-ID>

## Mode

Read-only. Do NOT modify any files during planning. Output a structured plan only.

## Output Format

Produce the following sections in order:

### 1. Goal
One sentence: what this feature delivers and why it matters now.

### 2. Business Context
Regulatory or product driver. Reference FCA rule, IL ticket, or stakeholder request.

### 3. Components Affected
List every service, module, API route, DB table, dbt model, and agent that will change.

### 4. Files to Inspect
Exact file paths to read before implementation starts. Include tests.

### 5. Implementation Approach
Step-by-step breakdown. Each step = one PR-sized unit of work. Note dependencies between steps.

### 6. Risks
Technical, compliance, and operational risks. For each: likelihood, impact, mitigation.

### 7. Tests Required
Specific test cases needed. Include positive, negative, and boundary cases for critical domains.

### 8. Documentation Updates
List every doc file that must be updated (API.md, runbooks, compliance, ADR).

### 9. Rollout / Rollback Plan
How to deploy safely. What to monitor. How to roll back if needed.

## Safety Section (REQUIRED if any of these are touched)

If the feature touches **AML/KYC, ledger, reporting, auth, secrets, or migrations**, add:

- **Compliance gate**: which control is affected and who must approve
- **Data risk**: what financial data is touched and how
- **Irreversibility**: what actions cannot be undone and what guard prevents accidents
- **Audit trail**: how this feature is logged for regulatory inspection
