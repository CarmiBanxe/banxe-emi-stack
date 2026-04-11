# /review-pr — Pull Request Review Command
# BANXE AI BANK | IL-SK-01
# Usage: /review-pr <PR-number-or-branch>

## Review Dimensions

Evaluate the PR across these dimensions:

| Dimension | What to check |
|-----------|---------------|
| **Correctness** | Does the code do what the ticket says? Edge cases handled? |
| **Security** | Hardcoded secrets? SQL injection? Unsafe eval? Shell injection? |
| **Regression** | Could this break existing behaviour? Are existing tests still valid? |
| **Test sufficiency** | Are the new/changed tests meaningful? Negative cases covered? |
| **Documentation** | API.md updated? Runbooks? Compliance docs? ADR if needed? |
| **Compliance / Audit** | Is every financial action logged? Is the audit trail intact? |

## Focus Areas (high risk — always inspect)

- Ledger operations (`services/ledger/`)
- AML / KYC decision logic (`services/aml/`, `services/kyc/`)
- Reporting and FIN060 (`services/reporting/`, `dbt/`)
- Auth and session management
- Secrets handling and environment variables
- Webhooks and external callbacks
- Database migrations

## Finding Classification

Classify every finding as one of:

| Class | Meaning |
|-------|---------|
| **BLOCKER** | Must be fixed before merge. Security, correctness, or compliance issue. |
| **IMPORTANT** | Should be fixed before merge. Significant risk if deferred. |
| **NICE-TO-HAVE** | Optional improvement. Can be a follow-up ticket. |

## Finding Format

For each finding:

```
[BLOCKER|IMPORTANT|NICE-TO-HAVE] <short title>
File: <path>:<line>
Problem: <what is wrong>
Why it matters: <business or compliance impact>
Fix direction: <how to resolve>
```

## Summary

End with: approved / approved with conditions / request changes, and count of blockers/importants.
