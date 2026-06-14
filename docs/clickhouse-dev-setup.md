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
