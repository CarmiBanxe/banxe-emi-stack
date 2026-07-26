# Statements Mask Policy — Operator Ratification Pack

**Date:** 2026-07-25 | **Scope:** `config/masks/statements-mask-policy.yaml` only
**Purpose:** the exact, minimal list of values an operator/compliance/legal/DPO/finance
owner must supply before the Statements governed cutover (Option B, final reroute step)
can be executed. Nothing in this document changes runtime code, fills in a value, or
activates the policy — it is a checklist, not an implementation.

## Current blocking status

`config/masks/statements-mask-policy.yaml` is `status: PROPOSED`. `build_statement_client_agent()`
(`services/client_statements/wiring.py`) fail-louds with `MaskPolicyNotReady` against this
exact file today (confirmed by `tests/test_client_statements_wiring.py::test_shipped_proposed_policy_refuses_to_build_live_agent`).
**8 fields are `null` and block `status: ACTIVE`.** No threshold, cap, or role value
below has been invented by code — every one requires a real decision from a real owner.

## Required fields, grouped

### 1. Cost caps (`cost_cap:` block)

| Field | Controls | Approval owner | Risk if empty / too permissive |
|---|---|---|---|
| `max_tokens_window` | Rolling-window (24h) token budget for all Statements agent activity | Finance + Engineering/Operator | Empty: agent cannot run at all. Too permissive: no real ceiling on compute cost per window. |
| `max_cost_window` | Rolling-window (24h) monetary spend ceiling (Decimal, GBP) | Finance | Empty: agent cannot run. Too permissive: unbounded real-money spend exposure per window. |
| `max_request_tokens` | Per-single-request token ceiling | Engineering/Operator | Empty: agent cannot run. Too permissive: one oversized request can consume an entire window's budget instantly. |
| `max_request_cost` | Per-single-request monetary ceiling (Decimal, GBP) | Finance | Empty: agent cannot run. Too permissive: one request can spend disproportionately before window tracking catches it. |

### 2. Confirmation thresholds (`confidence_bands:` block)

| Field | Controls | Approval owner | Risk if empty / too permissive |
|---|---|---|---|
| `auto_min_confidence` | Confidence at/above which an action proceeds AUTO, no human review | Compliance | Empty: agent cannot run. Set too low: client-fund/PII actions auto-proceed on low-confidence resolution — defeats the point of the mask. |
| `review_min_confidence` | Confidence at/above which a below-AUTO action steps to REVIEW rather than BLOCK | Compliance | Empty: agent cannot run. Set too low: low-confidence actions get routed to a human-review path instead of being blocked outright, weakening the safety margin. |

### 3. Delivery / data-egress materiality

**No blocking field exists in this policy for materiality.** Unlike the Analytics
policy (`config/masks/analytics-mask-policy.yaml`, which has an `export_materiality`
size/row-count threshold), the Statements mask gates data-egress purely by **delivery
channel** (see §5) — there is no separate size- or volume-based materiality dimension
in the current `StatementPort`/`StatementMask` contract. Nothing to ratify here; flagged
so this isn't mistaken for an oversight.

### 4. Escalation roles (`escalation_roles:` block)

| Field | Controls | Approval owner | Risk if empty / too permissive |
|---|---|---|---|
| `pii_compliance_block` | Who a `ComplianceBlock` (PII-overlay failure) escalates to | DPO / Legal | Empty: agent cannot run. Too permissive (e.g. no real accountable person, or an automated role): PII-blocked actions could stall with no real owner acting on them. |
| `data_egress_review` | Who reviews/approves EMAIL/EXPORT delivery of a PII-bearing funds statement | DPO / Legal / Compliance | Empty: agent cannot run. Too permissive (e.g. a non-human or rubber-stamp role): defeats the entire purpose of the REVIEW gate on external data egress. |

### 5. Delivery channel classification (`delivery_channel_classification:` block)

**Already resolved — not blocking, nothing to ratify.** `IN_APP: AUTO`, `EMAIL: REVIEW`,
`EXPORT: REVIEW` are already fixed by `StatementPort`'s own documented contract
(ADR-055 §D1), not invented values requiring a fresh decision. Listed here only for
completeness against the requested grouping.

## Proposed approval owners (summary)

- **Finance** — `max_cost_window`, `max_request_cost` (the two monetary caps).
- **Engineering/Operator** — `max_tokens_window`, `max_request_tokens` (the two token caps).
- **Compliance** — `auto_min_confidence`, `review_min_confidence`.
- **DPO / Legal** — `pii_compliance_block`, `data_egress_review`.

A single "operator" sign-off is not sufficient for all 8 fields — the monetary and
role fields specifically need the owner named above, not a general approval.

## Binding statement

**The final Statements reroute (pointing `api/routers/client_statements.py` at
`build_statement_client_agent()`) must NOT be activated before `config/masks/statements-mask-policy.yaml`
has real values for all 8 fields listed above AND `status:` is changed from `PROPOSED`
to `ACTIVE`.** `build_statement_client_agent()` already enforces this at code level
(`MaskPolicyNotReady`) — this document is the ratification record for who supplies
those values, not a bypass of that gate.
