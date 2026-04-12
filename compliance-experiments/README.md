# Compliance Experiments

Git-tracked experiment store for the Banxe Compliance Experiment Copilot (IL-CEC-01).

## Directory Structure

```
compliance-experiments/
├── draft/        ← DRAFT experiments (under design, not yet approved)
├── active/       ← ACTIVE experiments (approved, currently running)
├── finished/     ← FINISHED experiments (concluded, results logged)
├── rejected/     ← REJECTED experiments (declined by steward)
└── index.json    ← Auto-generated index (do NOT edit manually)
```

## File Format

Each experiment is stored as a YAML file named `{experiment_id}.yaml`:

```yaml
id: exp-2026-04-trans-reduce-false-po
title: "Transaction Monitoring: reduce false positives via velocity tuning"
scope: transaction_monitoring
status: draft
hypothesis: "By adjusting velocity thresholds..."
kb_citations:
  - eba-gl-2021-02
  - fatf-rec-10
created_by: compliance-officer@banxe.com
created_at: "2026-04-11T10:00:00"
updated_at: "2026-04-11T10:00:00"
metrics_baseline:
  hit_rate_24h: 0.25
  false_positive_rate: 0.75
  sar_yield: 0.10
metrics_target:
  hit_rate_24h: 0.35
  false_positive_rate: 0.60
  sar_yield: 0.15
tags:
  - velocity
  - false-positive-reduction
  - transaction_monitoring
```

## Lifecycle

```
DRAFT → (steward.approve) → ACTIVE → (metrics_reporter.auto_finish) → FINISHED
DRAFT → (steward.reject)  → REJECTED
ACTIVE → (steward.finish) → FINISHED
```

## Invariants

- Every status transition is logged in `data/audit/experiments.jsonl` (I-24)
- `index.json` is auto-regenerated on every save — never edit manually
- Experiments in `rejected/` and `finished/` are immutable (no further status changes)
- All ACTIVE experiments must have at least 1 KB citation (FCA evidence requirement)

## HITL Gates

| Transition | Required Approver | Gate Timeout |
|------------|------------------|--------------|
| DRAFT → ACTIVE | Compliance Officer / MLRO | 24h |
| ACTIVE → FINISHED | Automatic (metrics) or Steward | — |
| Any → REJECTED | Steward | 4h |

## References

- Experiment Copilot: `services/experiment_copilot/`
- Audit trail: `data/audit/experiments.jsonl`
- AML baselines: `config/aml_baselines.yaml`
- PR template: `config/templates/compliance_pr_template.md`
- API: `GET/POST /v1/experiments/*`
- MCP tools: `experiment_design`, `experiment_list`, `experiment_get_metrics`, `experiment_propose_change`
