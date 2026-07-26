# ADR-049: Mask-Policy Framework (§D2/§D3/§D4 mechanics) — SANDBOX

- Status: **DRAFT / SANDBOX-ONLY** — NOT ratified for production
- Date: 2026-07-26
- Deciders: Architecture (real sign-off PENDING)

> ⚠️ SANDBOX MARKING: This ADR is a NON-PROD placeholder created to unblock the
> statements/mask-policy layer in sandbox only. Values referenced here are Fable-advisor
> SANDBOX placeholders (config/masks/statements-mask-policy.sandbox.yaml), NOT ratified
> prod decisions. The shipped config/masks/statements-mask-policy.yaml remains PROPOSED.
> PROD CUTOVER FORBIDDEN until named owners (Architecture) sign off real values.

## Context
Generic mask-policy framework: boundary object (§D2), staged rollout (§D3), threshold reuse (§D4). Referenced by ADR-054/055 and services/shared/mask_policy.py.

## Decision (SANDBOX placeholder)
Adopt the config-as-data mask framework (status PROPOSED|ACTIVE, fail-loud MaskPolicyNotReady when ACTIVE+null). Sandbox confirms the mechanics load; framework shape unchanged from code.

## Consequences
- Positive: statements layer loads/builds in sandbox (dormant agent, no live MCP/API route).
- Negative / guard: real thresholds & roles still require owner sign-off; shipped policy stays PROPOSED; this ADR must be re-authored with real decisions before prod.

## Landing precondition (binding)
Prod cutover requires: real owner-signed values in the SHIPPED policy (not the .sandbox file),
status PROPOSED->ACTIVE on the shipped file, and this ADR re-issued as ratified (not SANDBOX).
