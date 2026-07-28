---
il_ts: 2026-07-28T09:30:00Z
session_id: passA-contracts-sbom
source: agent-factory
status: PROPOSED
---
### PASS A (STEP5+STEP6): oasdiff contract gate + CycloneDX SBOM (Fable 5 rollout)

- **Instruction:** One singleton PR delivering both producers. STEP5: context
  `contract-diff` — live OpenAPI (api.main:app) vs committed baseline
  apps/.openapi-snapshot.json via pinned oasdiff v1.26.1 + changed static specs
  (services/payment/openapi.yml) vs base revision; verdicts NON_BREAKING /
  BREAKING (fail without label api-breaking-ack) / UNKNOWN (generation or tool
  failure => visible FAIL, never silent pass — NO-MOCK); baseline refresh is
  intentional-only via contract_check.py --refresh-baseline (CI never
  auto-overwrites). STEP6: context `sbom` — CycloneDX via cyclonedx-bom==7.3.1
  (python, requirements mode) + @cyclonedx/cyclonedx-npm@6.0.0 (frontend,
  lock-only); 0-component SBOM = FAIL; artifact sbom-cyclonedx (14d);
  Dependency-Track upload OPTIONAL behind operator secrets DT_API_KEY+DT_URL,
  absent => documented degrade-to-skip SUCCESS.
- **Files:** .github/workflows/contracts-sbom.yml (new, all actions SHA-pinned),
  scripts/gitnexus/contract_check.py (new, stdlib, --check/--run/
  --refresh-baseline), config/gitnexus/ownership.map.json (append-only:
  contract_gate + sbom blocks + extension_points statuses; STEP2/3/4 keys
  untouched — gen_codeowners/scip_manifest checks green),
  docs/canon/GITNEXUS-STEP5-6-CONTRACTS-SBOM.md (new), this shard.
- **PRODUCER-ONLY:** neither context added to branch protection; PASS-A-c
  decides after observed green (STEP1..4 pattern).
- **Invariants:** I-24 (append-only; governance paths touched — this shard
  satisfies guardian-ledger); I-27 (BREAKING unblocked only by human-applied
  ack label); ADR-117 (emi-stack scope); ADR-060/120 (branch
  agent/factory/EMISTACK01/passA-contracts-sbom via dedicated worktree);
  singleton ledger-PR; Fable 5 (pins verified live: oasdiff release asset,
  pypi 7.3.1, npm 6.0.0; NO-MOCK; freshness via evidence artifacts).
- **Reference:** Fable 5 consultant response §2/§5/§6 roadmap steps 5–6;
  STEP1..4 shards; .claude/rules/20-api-contracts.md.
- **Status:** PROPOSED — operator merge required. No mint issued.
