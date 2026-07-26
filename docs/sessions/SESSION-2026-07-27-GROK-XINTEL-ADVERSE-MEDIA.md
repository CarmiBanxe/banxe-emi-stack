# SESSION 2026-07-27 — Grok-lane, X-intel, statements sandbox, multi-node adverse-media

STATUS: reference memory + guidance for future sessions. Records what exists, the canon
that governs it, and what remains a HUMAN decision.

## Commits (branch agent/factory/ledgerenv/sandbox-fix)
- 33b90c5 docs(fable-grok): ADR-043 Grok lane activation
- 8627805 feat(shared): mask_email (Grok smoke #1, ADR-043 L2)
- 9edaa63 feat(shared): mask_pan (Grok smoke #2, ADR-043 L2)
- 3c2d703 docs(blocker): register missing ADR-047/049/054/055
- d4bea4b feat(x-intel): configure x-agent-intelligence + X MCP
- b96459e feat(x-intel): first AI-intelligence feed snapshot
- c2d3158 fix(mcp): type:http for xapi
- 07df1f4 feat(statements): sandbox-activate mask-policy (SANDBOX-ONLY)
- 56742fb feat(adverse-media): X OSINT feed (SANDBOX-off, MLRO-HITL)
- 0d4d723 feat(adverse-media): multi-node feeds RSS+Web+Composite

## Architecture in place
- Grok lane (ADR-043): Fable=advisor, grok-implementer=executor, operator=L2. Sandbox/local.
- X intelligence feed: control-plane, ring-fenced, outside client-data. feed.html via xapi MCP.
- Statements mask-policy: shipped=PROPOSED (contract); statements-mask-policy.sandbox.yaml=ACTIVE
  (Fable SANDBOX placeholders); ADR-047/049/054/055 DRAFT/SANDBOX-ONLY; agent dormant.
- Adverse-media: NegativeNewsFeed Protocol; CompositeFeed aggregates OpenSanctions+X+RSS+Web;
  all SANDBOX-off, XXE-safe, secrets env-only, advisory-only.

## Adverse-media agent hierarchy (Fable advisory 2026-07-27) — two-stage: research below, judgment above
- Stage 1 RESEARCH — CDD Review Agent (human double: Compliance Officer) commands CompositeFeed
  via AdverseMediaService, assembles a DOSSIER. L2, advisory, no customer-state change.
- HANDOFF — dossier becomes the MLRO HITL case payload.
- Stage 2 DECISION — MLRO (L4, SMF17) decides. No auto-clear/auto-block.
- Rationale: SMCR SMF17 decision independence (MLRO not investigator-and-judge);
  MLR 2017 Reg.28 EDD = compliance function; SYSC 6.3.9R MLRO oversight.
- The feed agent does NOT take tasking from MLRO; MLRO only receives the dossier.
- Triggers: (1) onboarding risk>=MEDIUM (I-04 EDD); (2) periodic re-screening
  (services/compliance_automation/periodic_review.py — adverse_media not yet wired = next step).

## CANON (guidance to action)
- One artifact per operator turn (SHELL or CLAUDE CODE); next only after operator output.
- Factory/Grok writes code; operator commits; secrets/creds/prod = operator only.
- fail-closed: never fake prod values; missing ADR/threshold blocks landing.
- Every commit passes Semgrep gate. .env never committed.

## OPEN — HUMAN decisions only
1. X-feed cron: headless ready; BLOCKED until Spend Cap set in X Billing (currently Unlimited).
2. Prod cutover (statements / any adverse-media node): needs Finance+Compliance+DPO+MLRO
   sign-off + UK-GDPR lawful-basis assessment + re-issue SANDBOX ADRs as ratified.
3. Wire adverse_media into periodic_review for ongoing monitoring (Stage 1 CDD-owned).
