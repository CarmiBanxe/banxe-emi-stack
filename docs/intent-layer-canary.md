# Intent Layer — staging canary (FU-2 Phase 5)

> **Status (FU-2 Phase 5):** the ADR-049 L1 Intent Layer moves from **dark mode**
> (Phase 3) to a **tightly-scoped, observable canary** — enabled **in staging only**,
> for **one low-risk capability** (Notifications). Production stays dark. There is **no**
> activation for payments / FX / wallet / KYC / SAR / sanctions in this phase, and a
> single flag change reverts to dark mode. See [`intent-layer-dev.md`](./intent-layer-dev.md)
> for the dark-mode baseline.

## What the canary does

When the layer is enabled for an environment, an **auto-dispatch gate** decides which
resolved capabilities may actually flow to an L2 mask. Two mechanistic checks — in code,
never via prompt — run in safety order:

1. **High-risk denylist (hard, non-configurable).** Any capability touching money
   movement, FX, wallet/balance, cards, KYC/onboarding, SAR or sanctions/AML screening
   is **never** auto-dispatched. It is routed to the human/manual (governance) flow.
   The denylist wins **even if such a capability is mistakenly added to the allowlist.**
   It matches on an explicit capability-key set **and** a token scan over the capability
   label + matched intent, so a newly-added or mislabelled high-risk capability is still
   caught. (`services/intent_layer/canary.py`)
2. **Canary allowlist (default-deny).** `INTENT_LAYER_CANARY_CAPABILITIES` lists the
   capability keys allowed to auto-dispatch. **Empty by default**, so an enabled-but-
   unconfigured layer dispatches nothing — a leaked global flag in prod stays
   mechanically dark.

Anything withheld degrades to the **current behaviour**: high-risk → governance event;
not-in-canary → the same `NOT_ENABLED` no-op shape as dark mode. The HTTP response schema
is unchanged, so there is no customer-facing SLA change.

## Flags

| Flag | Where defined | Default | Purpose |
| --- | --- | --- | --- |
| `INTENT_LAYER_ENABLED` | `services/intent_layer/config.py` | `false` | Global master flag (legacy/back-compat) |
| `APP_ENV` (or `ENVIRONMENT`) | `services/intent_layer/config.py` | `production` | Names the deployment environment |
| `INTENT_LAYER_ENABLED_<ENV>` | `services/intent_layer/config.py` | unset | Per-env override (e.g. `INTENT_LAYER_ENABLED_STAGING`); wins over the global flag for that env only |
| `INTENT_LAYER_CANARY_CAPABILITIES` | `services/intent_layer/canary.py` | empty | Comma-separated allowlist of capability keys permitted to auto-dispatch |

The high-risk denylist is **not** a flag — it is hard-coded in `canary.py`
(`HIGH_RISK_CAPABILITY_KEYS` + `HIGH_RISK_TOKENS`) and cannot be relaxed by config.

## Enable / disable in staging (env changes only)

**Enable the canary in staging:**

```bash
APP_ENV=staging
INTENT_LAYER_ENABLED_STAGING=true
INTENT_LAYER_CANARY_CAPABILITIES=Notifications
# (optional) durable lineage:
DECISION_RECORDER=clickhouse
```

**Roll back to dark mode (instant):** flip the per-env flag back —

```bash
INTENT_LAYER_ENABLED_STAGING=false   # or unset it
```

No code change, no deploy: the flag is read fresh on each request, so the next request
returns to the dark-mode `NOT_ENABLED` behaviour. Production is unaffected throughout —
it never sets `INTENT_LAYER_ENABLED_PRODUCTION` and the staging override does not leak
across environments.

## Monitoring

* **Structured logs** (`LoggingCanaryObserver`, logger `banxe.intent_layer.canary`): one
  record per gate decision — `decision`, `capability_key`, `correlation_id`. High-risk
  withholds log at **WARNING** for alerting. No intent text or PII is logged.
* **Counters** (`CounterCanaryObserver`), exposed read-only at
  `GET /v1/intent/canary/metrics`:

  ```json
  {
    "canary_intents_total": 0,
    "canary_dispatched": 0,
    "canary_withheld_not_canary": 0,
    "canary_withheld_high_risk": 0,
    "canary_errors": 0
  }
  ```

  These give canary volume, dispatch vs withhold split, and the error count.

## Tests

```bash
pytest tests/test_intent_layer/test_canary.py \
       tests/test_intent_layer/test_canary_metrics.py \
       tests/test_intent_layer/test_config.py \
       tests/test_intent_layer/test_router.py \
       tests/test_canary_api.py -v
```
