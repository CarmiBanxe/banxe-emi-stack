# Watchdog MVP — Sprint 2

Efficiency-aware health monitor for BANXE inference nodes (evo1/evo2).

## I-27 Boundary

| Action | Policy | Notes |
|---|---|---|
| Warm cold model | AUTO | backoff [10,30,120]s, max 3 attempts |
| Log to ledger | AUTO | append-only jsonl |
| Escalate | AUTO | structured alert + optional webhook |
| Restart ollama | OPERATOR ONLY | never autonomous |
| Reroute LiteLLM alias | OPERATOR ONLY | never autonomous |
| Evict model from VRAM | OPERATOR ONLY | never autonomous |

## Efficiency Metric Definitions

| Metric | Formula | Source |
|---|---|---|
| tokens_per_sec | eval_count / (eval_duration / 1e9) | Ollama /api/generate |
| hot_latency_s | total_duration / 1e9 | Ollama /api/generate |
| cold_start_s | load_duration / 1e9 | Ollama /api/generate |
| success_rate | rolling(correct_count / total) over 20 probes | internal |
| correctness | expect_contains in response | configurable probe |

## Node States

HEALTHY → COLD → (LOADING) → HEALTHY (auto-warm)
HEALTHY → SLOW / DEGRADED / INCORRECT → ESCALATE (operator action required)
HEALTHY → UNREACHABLE → ESCALATE

## VRAM Note

`rocm-smi` is UNRELIABLE on evo1 (AMD unified memory: reports per-die slice, not aggregate).
VRAM occupancy is inferred from `/api/ps` model list + known model sizes.

## Config

`services/watchdog/watchdog.yaml` — probe intervals, thresholds, node list, autonomy policy.

## References

- Sprint 2 spec: `/tmp/BANXE-REPAIR-BRIGADE-ROADMAP.md`
- I-27: `services/hitl/hitl_service.py`
- Agent authority: `.claude/rules/agent-authority.md`
- Topology source: VoI 2026-07-07 (evo1:2222/banxe, evo2:22/moriel-carmi, legion:local)
