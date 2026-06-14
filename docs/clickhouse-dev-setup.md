# ClickHouse — local dev baseline (FU-2 step 1)

**Status:** prep only. This document records how to bring up a local ClickHouse
instance on a dev host (Legion) as a prerequisite for future
`ClickHouseDecisionRecorder` work in the Intent Layer.

> **Not implemented yet (out of scope for this step):**
> - `ClickHouseDecisionRecorder` wiring.
> - Any schema / migrations / `docker-entrypoint-initdb.d` seeding.
> - `INTENT_LAYER_ENABLED` / `DECISION_RECORDER` env flags (unchanged).
> - Any live HTTP wiring between emi-stack and `banxe-payment-core`.
>
> This PR is documentation only — it confirms ClickHouse can be started
> locally and health-checked. No application code or config is changed.

## Service definition

ClickHouse is defined as a standalone service (no `depends_on`, no volumes) in
[`docker/docker-compose.master.yml`](docker/docker-compose.master.yml):

```yaml
clickhouse:
  image: clickhouse/clickhouse-server:24.3-alpine
  ports:
    - "9000:9000"   # native protocol
    - "8123:8123"   # HTTP interface
  healthcheck:
    test: ["CMD-SHELL", "clickhouse-client --query 'SELECT 1'"]
    interval: 10s
    timeout: 5s
    retries: 5
```

## Bring up ClickHouse only

Start **only** the ClickHouse service (no postgres / redis / api / frankfurter):

```bash
docker compose -f docker/docker-compose.master.yml up -d clickhouse
```

### Host port note (Legion)

On the Legion dev host, host port `9000` is already held by an unrelated
process (an SSH local forward). When that collision occurs, run the same
service under an isolated project name with a small **uncommitted** override
that remaps the native port (HTTP `8123` is kept for health checks):

```yaml
# /tmp/clickhouse-dev-override.yml  (do NOT commit)
services:
  clickhouse:
    ports: !override
      - "8123:8123"
      - "19000:9000"
```

```bash
docker compose -p ch-dev \
  -f docker/docker-compose.master.yml \
  -f /tmp/clickhouse-dev-override.yml \
  up -d clickhouse
```

## Expected ports

| Port    | Interface           | Notes                                  |
| ------- | ------------------- | -------------------------------------- |
| `8123`  | HTTP                | health/ping; queries need a non-local user |
| `9000`  | native protocol     | remap to `19000` on Legion (see above) |

## Health check

```bash
# 1. HTTP ping (no auth) — expect: Ok.
curl -sf http://localhost:8123/ping

# 2. Native SELECT 1 (matches the compose healthcheck) — expect: 1
docker exec <clickhouse-container> clickhouse-client --query "SELECT 1"

# 3. Container health — expect: STATUS "Up ... (healthy)"
docker ps --filter name=clickhouse
```

> The bundled image ships `users.d/default-user.xml`, which restricts the
> `default` user to `127.0.0.1` / `::1`. The in-container healthcheck and
> `/ping` therefore succeed, while host-side HTTP **queries** are rejected
> until a non-localhost user is configured — that user setup is part of the
> later `ClickHouseDecisionRecorder` step, not this baseline.

## Tear down

```bash
docker compose -p ch-dev -f docker/docker-compose.master.yml down
```

## `ClickHouseDecisionRecorder` (FU-2 step 2) — flagged, OFF by default

> ⚠️ **The Intent Layer stays dark.** `INTENT_LAYER_ENABLED` MUST remain `false`
> until a later, explicit activation FU. The recorder below is a durable lineage
> *sink* only — selecting it does **not** enable the Intent Layer and does not
> change any live client dispatch.

The decision-lineage sink is selected by the `DECISION_RECORDER` env var:

| `DECISION_RECORDER` | Sink                            | Default |
| ------------------- | ------------------------------- | ------- |
| unset / `inmemory`  | `InMemoryDecisionRecorder`      | ✅ yes  |
| `clickhouse`        | `ClickHouseDecisionRecorder`    | no      |

With the var unset (or `inmemory`) the system behaves exactly as before — an
in-process, append-only list. Any other value fails closed (raises), so a typo
can never silently downgrade durability.

### 1. Apply the schema

Create `banxe.decision_records` (additive — no existing table is touched):

```bash
# native client (port 9000 / 19000 on Legion — see above)
clickhouse-client --multiquery < infra/clickhouse/migrations/006_create_decision_records.sql
# …or over HTTP
curl -sf 'http://localhost:8123/' --data-binary @infra/clickhouse/migrations/006_create_decision_records.sql
```

### 2. Enable it locally

```bash
export DECISION_RECORDER=clickhouse
export CLICKHOUSE_HOST=localhost
export CLICKHOUSE_PORT=9000        # 19000 under the Legion override
export CLICKHOUSE_DB=banxe
export CLICKHOUSE_USER=default
export CLICKHOUSE_PASSWORD=        # set if a non-localhost user is configured
pip install clickhouse-driver      # only needed for the clickhouse sink
```

`get_decision_recorder()` (in `services/agents/recorders.py`) is the composition
seam: it reads `DECISION_RECORDER` and returns the chosen
[`DecisionRecorder`](../services/agents/_lineage.py). The driver client is built
lazily from the `CLICKHOUSE_*` config, so no socket is opened until the first
`record()`/`query()`.

### 3. Run the tests

The recorder unit tests use an in-process fake client and need **no** ClickHouse:

```bash
pytest tests/agents/test_recorders.py -q
```

To exercise a real round-trip (insert + read-back) against a dev ClickHouse,
apply migration 006, then set the opt-in DSN marker and run:

```bash
export DECISION_RECORDER_TEST_DSN=1   # any truthy value un-skips the live test
pytest tests/agents/test_recorders.py::test_clickhouse_live_round_trip -q
```

Without `DECISION_RECORDER_TEST_DSN` the live test is **skipped**, so CI stays
green on environments without ClickHouse.
