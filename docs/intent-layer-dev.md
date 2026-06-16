# Intent Layer — developer guide (dark-mode testing & dry-run)

> **Status (FU-2 Phase 3):** the ADR-049 L1 Intent Layer ships **inert**.
> `INTENT_LAYER_ENABLED` is **`false` in every environment** and this phase does
> **not** activate it for real traffic. The work here is tests + tooling only:
> a way to exercise classification/routing/lineage end-to-end while the layer stays dark.

## What "dark mode" means

With `INTENT_LAYER_ENABLED=false` (the default):

| Stage | Behaviour while dark |
| --- | --- |
| HTTP `POST /v1/intent` | Accepts the request, returns `{"enabled": false, "disposition": "NOT_ENABLED"}` |
| `IntentRouter.route()` | Returns `NOT_ENABLED` **before** any dispatch — the flag gate is checked first |
| `IntentClassifier` | Deterministic match still runs; the **LLM fuzzy fallback is suppressed** |
| `AgentDispatchPort` | **Never called** — no L2 mask, no payment-core adapter, no outbound call |
| Lineage sink | **Nothing recorded** — neither in-memory nor ClickHouse, even with `DECISION_RECORDER=clickhouse` |

The flag is distinct from ADR-021's `AGENT_ROUTING_ENABLED` (the internal
compliance task-router) — the two layers must never share a flag.

## Running the dark-mode tests

```bash
# The dedicated dark-mode module (pure layer + HTTP entrypoint):
pytest tests/test_intent_layer/test_intent_layer_dark_mode.py -v

# The whole Intent Layer suite (classifier, router, composition, e2e, dark mode):
pytest tests/test_intent_layer/ -v
```

The tests inject **exploding doubles** — an `AgentDispatchPort`, an `LLMClassifierPort`
and a `ClickHouseClient` that each raise if ever called — so any external side effect
in dark mode fails the test loudly instead of happening silently.

### ClickHouse-dependent tests (opt-in)

Lineage tests that need a live ClickHouse are **skipped** unless a DSN is provided, so
CI stays green without ClickHouse:

```bash
# Opt in to the live ClickHouse round-trip + dark-mode "records nothing" check:
DECISION_RECORDER_TEST_DSN=clickhouse://localhost:9000/banxe \
  pytest tests/test_intent_layer/test_intent_layer_dark_mode.py tests/agents/test_recorders.py -v
```

`DECISION_RECORDER=clickhouse` only *selects* the durable sink — it does **not** enable
the Intent Layer. `INTENT_LAYER_ENABLED` stays `false`.

## Dry-run CLI (`scripts/intent_layer_dryrun.py`)

A **developer-only** tool (not a production entrypoint) to explore how an intent
classifies and routes, while the layer stays dark. It drives the *same* internal
entrypoint the HTTP handler uses, with an **inert simulating dispatcher** that never
touches a real mask, adapter, the network, or ClickHouse.

```bash
# Pipe a JSON payload:
echo '{"intent_text": "send money"}' | python scripts/intent_layer_dryrun.py

# Or pass the text directly:
python scripts/intent_layer_dryrun.py --intent "freeze my card"

# Read what WOULD happen if the layer were enabled (report only — still no real dispatch):
python scripts/intent_layer_dryrun.py --intent "exchange" --force-simulate

# Machine-readable output:
python scripts/intent_layer_dryrun.py --intent "notifications" --json
```

Example (dark, default):

```
=== Intent Layer dry-run (DEV TOOL — no real dispatch) ===
intent_text          : 'send money'
correlation_id       : 9f3c…
INTENT_LAYER_ENABLED : false  (actual env flag)
mode                 : DARK
-- classification --
  status             : RESOLVED
  matched_intent     : pay
  capability / mask  : Payments
  confidence / band  : 1.00 / AUTO
  match_source       : ALIAS
  process_refs       : payment-processing-process@1.0.0
-- routing --
  disposition        : NOT_ENABLED
  would dispatch if enabled : yes
  real dispatch performed   : NO (dry-run never touches a mask/adapter/ClickHouse)
```

> Classification is deterministic (exact/alias match against the intent→process map).
> Free-form phrasing like `"send money to Alice"` resolves to `UNRESOLVED` until the
> S1 LLM fuzzy fallback is wired — and that fallback is itself suppressed while dark.

- **`--force-simulate`** only changes the *report* (it lets the classifier/router
  reason as if enabled); the dispatcher remains a no-op simulator, so no live mask,
  adapter, network call, or ClickHouse write ever happens.
- The catalogue is loaded from the live S3 files when `INTENT_PROCESS_MAP_PATH` +
  `INTENT_PROCESS_REGISTRY_PATH` are set, otherwise from the embedded snapshot.

## What this phase does NOT do

- It does **not** set `INTENT_LAYER_ENABLED=true` anywhere.
- It does **not** change any production env default or public API contract.
- It does **not** touch `banxe-architecture` or `banxe-payment-core`.

Real activation (live cross-repo masks, real L3, the S1 LLM gateway, the ClickHouse
sink in production) is a later, separate operator step.
