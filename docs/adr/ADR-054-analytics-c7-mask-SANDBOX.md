# ADR-054: Analytics/Reporting (C7) Mask — data-egress posture — SANDBOX

- Status: **DRAFT / SANDBOX-ONLY** — NOT ratified for production
- Date: 2026-07-26
- Deciders: Documentary (Architecture) (real sign-off PENDING)

> ⚠️ SANDBOX MARKING: This ADR is a NON-PROD placeholder created to unblock the
> statements/mask-policy layer in sandbox only. Values referenced here are Fable-advisor
> SANDBOX placeholders (config/masks/statements-mask-policy.sandbox.yaml), NOT ratified
> prod decisions. The shipped config/masks/statements-mask-policy.yaml remains PROPOSED.
> PROD CUTOVER FORBIDDEN until named owners (Documentary (Architecture)) sign off real values.

## Context
Analytics/Reporting (C7) mask whose data-egress/export gate posture StatementPort.deliver_statement reuses; its §D5 deferred Statements to ADR-055.

## Decision (SANDBOX placeholder)
Confirm §D5 deferral to ADR-055 is the intended handoff. No blocking field owned here (cost=047, confidence/roles=055).

## Consequences
- Positive: statements layer loads/builds in sandbox (dormant agent, no live MCP/API route).
- Negative / guard: real thresholds & roles still require owner sign-off; shipped policy stays PROPOSED; this ADR must be re-authored with real decisions before prod.

## Landing precondition (binding)
Prod cutover requires: real owner-signed values in the SHIPPED policy (not the .sandbox file),
status PROPOSED->ACTIVE on the shipped file, and this ADR re-issued as ratified (not SANDBOX).
