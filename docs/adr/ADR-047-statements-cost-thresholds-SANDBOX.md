# ADR-047: AI Cost Governance — Statements Cost Thresholds — SANDBOX

- Status: **DRAFT / SANDBOX-ONLY** — NOT ratified for production
- Date: 2026-07-26
- Deciders: Finance + Engineering/Operator (real sign-off PENDING)

> ⚠️ SANDBOX MARKING: This ADR is a NON-PROD placeholder created to unblock the
> statements/mask-policy layer in sandbox only. Values referenced here are Fable-advisor
> SANDBOX placeholders (config/masks/statements-mask-policy.sandbox.yaml), NOT ratified
> prod decisions. The shipped config/masks/statements-mask-policy.yaml remains PROPOSED.
> PROD CUTOVER FORBIDDEN until named owners (Finance + Engineering/Operator) sign off real values.

## Context
Per-request and per-window cost/token caps for the statements agent (cost_cap block).

## Decision (SANDBOX placeholder)
SANDBOX placeholders: max_tokens_window=2000000, max_cost_window=GBP 40.00, max_request_tokens=250000, max_request_cost=GBP 5.00 (Decimal strings, I-01). Real caps pending Finance/Eng.

## Consequences
- Positive: statements layer loads/builds in sandbox (dormant agent, no live MCP/API route).
- Negative / guard: real thresholds & roles still require owner sign-off; shipped policy stays PROPOSED; this ADR must be re-authored with real decisions before prod.

## Landing precondition (binding)
Prod cutover requires: real owner-signed values in the SHIPPED policy (not the .sandbox file),
status PROPOSED->ACTIVE on the shipped file, and this ADR re-issued as ratified (not SANDBOX).
