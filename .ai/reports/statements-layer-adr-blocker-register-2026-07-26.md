# Statements/Mask-Policy Layer — ADR Blocker Register

- Date: 2026-07-26
- Status: BLOCKED (stashed as stash@{0})
- Source of truth: git stash show -p stash@{0}

## Fact (registry-completeness audit)

The stashed statements/mask-policy layer references 4 ADRs. ALL are MISSING on disk:

| ADR | Role (per code refs) | Owner(s) to author | Exists |
|-----|----------------------|--------------------|--------|
| ADR-049 | Generic mask framework (§D2/§D3/§D4 mechanics) | Architecture | NO |
| ADR-047 | AI cost thresholds (per-request / per-window caps) | Finance + Engineering | NO |
| ADR-054 | Analytics/Reporting (C7) mask; §D5 defers Statements to 055 | Documentary | NO |
| ADR-055 | Statements client-facing mask (§D1-§D4) | Compliance + DPO/Legal | NO |

## 8 policy fields still null (config/masks/statements-mask-policy.yaml, status: PROPOSED)

| Field | Block | Owner | ADR |
|-------|-------|-------|-----|
| max_tokens_window | cost_cap | Engineering/Operator | 047 |
| max_cost_window | cost_cap | Finance | 047 |
| max_request_tokens | cost_cap | Engineering/Operator | 047 |
| max_request_cost | cost_cap | Finance | 047 |
| auto_min_confidence | confidence_bands | Compliance | 055 |
| review_min_confidence | confidence_bands | Compliance | 055 |
| pii_compliance_block | escalation_roles | DPO/Legal | 055 |
| data_egress_review | escalation_roles | DPO/Legal | 055 |

## Landing precondition (binding)

Layer lands ONLY when: 4 ADRs authored+signed by named owners AND 8 fields filled AND
status PROPOSED -> ACTIVE (removes MaskPolicyNotReady). Not an agent task — human governance.

## Explicitly NOT done

No ADR values invented. No skeletons written referencing further phantom ADRs. Stash untouched.
