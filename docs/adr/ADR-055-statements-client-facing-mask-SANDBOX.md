# ADR-055: Statements Client-Facing Mask (§D1-§D4) — SANDBOX

- Status: **DRAFT / SANDBOX-ONLY** — NOT ratified for production
- Date: 2026-07-26
- Deciders: Compliance + DPO/Legal (real sign-off PENDING)

> ⚠️ SANDBOX MARKING: This ADR is a NON-PROD placeholder created to unblock the
> statements/mask-policy layer in sandbox only. Values referenced here are Fable-advisor
> SANDBOX placeholders (config/masks/statements-mask-policy.sandbox.yaml), NOT ratified
> prod decisions. The shipped config/masks/statements-mask-policy.yaml remains PROPOSED.
> PROD CUTOVER FORBIDDEN until named owners (Compliance + DPO/Legal) sign off real values.

## Context
Contract StatementPort is built against: §D1 read/generate/deliver allow-list, §D2 boundary, §D3 staged wiring, data-egress gate. Confidence bands + escalation roles owned here.

## Decision (SANDBOX placeholder)
SANDBOX placeholders: auto_min_confidence=0.95, review_min_confidence=0.80; escalation pii_compliance_block=DPO, data_egress_review=Compliance Officer. Delivery channels (IN_APP AUTO / EMAIL,EXPORT REVIEW) fixed by §D1. Real values pending Compliance/DPO.

## Consequences
- Positive: statements layer loads/builds in sandbox (dormant agent, no live MCP/API route).
- Negative / guard: real thresholds & roles still require owner sign-off; shipped policy stays PROPOSED; this ADR must be re-authored with real decisions before prod.

## Landing precondition (binding)
Prod cutover requires: real owner-signed values in the SHIPPED policy (not the .sandbox file),
status PROPOSED->ACTIVE on the shipped file, and this ADR re-issued as ratified (not SANDBOX).
