# Intent Layer — canary observability & rollback (FU-2 Phase 6)

> **Status (FU-2 Phase 6):** observability + safety instrumentation for the ADR-049
> L1 Intent Layer **canary** (the Notifications-in-staging path) and the S1
> LLM-gateway calls it makes. This phase adds metrics/logs/queries/dashboards and a
> written rollback policy. It does **not** widen the canary, add capabilities, or
> flip `INTENT_LAYER_ENABLED` anywhere. Prod stays dark.

This is the gate you read **before** expanding the canary beyond Notifications: it
defines what "the canary is behaving" means in concrete, queryable terms, and the
exact thresholds that trigger a rollback.

---

## 1. What is the canary?

| | |
| --- | --- |
| **Surface** | `POST /v1/intent` (`api/routers/intent.py`) |
| **In-process capability** | **Notifications only** (`_LIVE_HANDLERS = {"Notifications": …}`) — a low-consequence channel-availability *read*. Payments/FX/Wallet are cross-repo and return an honest *unrouted* receipt. |
| **Activation** | `INTENT_LAYER_ENABLED=true` — **staging only**. Prod stays `false` (dark). |
| **Gateway** | The S1 LLM fuzzy-fallback seam (`LLMClassifierPort`). Default `NullLLMClassifier` (abstains); a live gateway adapter is injected at the operator runtime step. |

The canary is enabled *only* in staging, so **gating emission on "enabled" is gating
on staging** — no second flag, and prod emits nothing.

---

## 2. Metric set

Defined in `services/intent_layer/observability.py` (names are module constants).
Metrics flow through `CanaryMetricsPort` (DI); the default sink is a no-op
(`NullCanaryMetrics`), so a backend is touched only when one is wired
(`CANARY_METRICS=inmemory` for local/staging diagnostics; a real Prometheus/StatsD/
ClickHouse port at the operator runtime step).

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `intent_layer_canary_requests_total` | counter | `capability`, `env`, `disposition` | Canary traffic volume per disposition (`DISPATCHED` / `GOVERNANCE_EVENT`). |
| `intent_layer_canary_errors_total` | counter | `capability`, `env`, `reason` | Failed dispositions (e.g. `dispatch_rejected`). |
| `intent_layer_canary_latency_ms` | observation | `capability`, `env` | classify+route+dispatch latency → p50/p95. |
| `intent_layer_canary_guardrail_triggers_total` | counter | `capability`, `env`, `reason` | Safety-violation signal: `compliance_fail` / `compliance_escalate` / `high_risk`. |
| `llm_gateway_request_latency_ms` | observation | `env` | S1-gateway call latency (only when a live gateway is wired). |
| `llm_gateway_errors_total` | counter | `env`, `reason` | S1-gateway call failures, keyed by exception type. |

**Not yet available — `mismatch_count`.** A canary-vs-baseline comparator would need a
shadow/baseline decision to diff against. No such comparator exists today (Notifications
is a read with no prior automated baseline), so this metric is intentionally **omitted
rather than fabricated**. Add it when a baseline comparator is introduced.

### Structured logs (always-on, no backend required)

* Logger `banxe.intent_layer.canary` — one line per live disposition with fields:
  `env, capability, disposition, outcome (success|error), compliance, high_risk,
  latency_ms, tenant, correlation_id` (+ `guardrail=<reason>` when triggered).
* Logger `banxe.llm_gateway` — one line per gateway call: `env, latency_ms, matched`
  (or `error=<type>` on failure).

R-SEC: labels/logs carry **only** opaque governance fields — never intent text, PII,
secrets, or a raw subject identity.

---

## 3. Queries

The durable backend available **today** is `banxe.decision_records` (ClickHouse
migration 006), written when the canary runs with `DECISION_RECORDER=clickhouse`. The
canary's emitting mask is `agent_id = 'notification_agent'`. These queries work now;
the latency/gateway panels additionally need the metrics port wired (operator step).

```sql
-- Canary traffic volume over time (hourly), last 24h
SELECT toStartOfHour(timestamp) AS hour, count() AS requests
FROM banxe.decision_records
WHERE agent_id = 'notification_agent' AND timestamp >= now() - INTERVAL 24 HOUR
GROUP BY hour ORDER BY hour;

-- Error / guardrail rate: share of non-PASS compliance results (last 24h)
SELECT
  countIf(compliance_result != 'PASS') AS guardrail_triggers,
  count() AS total,
  round(100 * guardrail_triggers / nullIf(total, 0), 2) AS guardrail_pct
FROM banxe.decision_records
WHERE agent_id = 'notification_agent' AND timestamp >= now() - INTERVAL 24 HOUR;

-- Compliance-result breakdown (PASS / FAIL / ESCALATE / N/A)
SELECT compliance_result, count() AS cnt
FROM banxe.decision_records
WHERE agent_id = 'notification_agent' AND timestamp >= now() - INTERVAL 24 HOUR
GROUP BY compliance_result ORDER BY cnt DESC;

-- Before/after comparison: enable-window vs the prior equal window
SELECT
  if(timestamp >= now() - INTERVAL 24 HOUR, 'after', 'before') AS window,
  count() AS requests,
  countIf(compliance_result != 'PASS') AS guardrail_triggers,
  round(avg(confidence_score), 3) AS avg_confidence
FROM banxe.decision_records
WHERE agent_id = 'notification_agent' AND timestamp >= now() - INTERVAL 48 HOUR
GROUP BY window ORDER BY window;
```

Latency p50/p95 and gateway error-rate come from the metrics backend once wired, e.g.
(PromQL, illustrative):

```promql
histogram_quantile(0.95, sum(rate(intent_layer_canary_latency_ms_bucket[5m])) by (le))
sum(rate(llm_gateway_errors_total[5m])) / sum(rate(llm_gateway_request_latency_ms_count[5m]))
```

### Dashboard-as-code

`infra/grafana/dashboards/intent-layer-canary.json` — a Grafana dashboard (ClickHouse
datasource) with the traffic, guardrail-rate, compliance-breakdown and confidence
panels above. It follows the same provisioning convention as
`agent-routing-metrics.json` (`infra/grafana/dashboards/dashboard.yml`).

---

## 4. Rollback policy (FU-2 canary — staging Notifications)

**Success criteria** (all must hold over a rolling 24h enable window vs the prior 24h
baseline window):

* **Error rate:** `intent_layer_canary_errors_total / requests_total` ≤ **1%**, and not
  more than **+0.5pp** above the baseline window.
* **Guardrail triggers:** no spike — `guardrail_triggers_total` rate ≤ **2×** the
  baseline window, and zero `compliance_fail` for the Notifications read (a read should
  never FAIL compliance).
* **Latency:** canary p95 ≤ **750 ms** and gateway p95 ≤ **2 s** (when a live gateway is
  wired).
* **Gateway:** `llm_gateway_errors_total` rate ≤ **2%**.

**Rollback triggers** — ANY one, sustained over ≥10 min (or a single hard breach):

* error rate > **2%**, or any `compliance_fail` on the Notifications canary;
* guardrail-trigger rate > **3×** baseline;
* canary p95 > **1.5 s** or gateway error rate > **5%**.

**Rollback mechanism — flags/env only, no code change, no deploy:**

1. Set `INTENT_LAYER_ENABLED=false` in the staging environment. The very next request
   short-circuits to `NOT_ENABLED` **before** any dispatch — no L2 mask, no gateway
   call, no lineage write, no canary metric/log. (This is the safe pre-activation
   contract proven by the dark-mode tests.)
2. Optionally set `CANARY_METRICS` back to `null` to silence the metrics sink.

No `INTENT_LAYER_CANARY_CAPABILITIES` change and no prod flip is involved in either
activation or rollback. Widening the canary beyond Notifications is a **separate**
future step, gated on this dashboard staying green across a full enable window.
