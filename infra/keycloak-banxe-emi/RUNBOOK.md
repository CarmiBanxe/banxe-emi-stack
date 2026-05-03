# RUNBOOK — Keycloak banxe-emi Realm
# ADR-017 / ADR-022 | I-34 / I-35 | INV-IAM-01 / INV-IAM-02
# FCA CASS 15 | Deadline: 7 May 2026
# Version: 2026-05-03 (pre-GATE-A)

## Overview

This runbook covers the full lifecycle of the `banxe-emi` Keycloak realm:
- Pre-flight state (current: KC 26.2.5 running on evo1:8180, HTTP 500)
- GATE-A remediation options
- Realm import (GATE-A → GATE-B)
- Client provisioning (GATE-B)
- Smoke test
- Backout / rollback (GATE-D)

Keycloak is the **single IAM issuer** (I-35) for all EMI service-to-service auth.
All 4 EMI service accounts use `client_credentials` grant (no user sessions).

---

## Prerequisites

| Requirement | Check |
|-------------|-------|
| evo1 accessible | `ssh banxe@evo1` |
| `~/.banxe/keycloak.env` exists, mode 600 | `stat ~/.banxe/keycloak.env` |
| KC_BOOT_ADMIN, KC_BOOT_ADMIN_PASSWORD set | `source ~/.banxe/keycloak.env && echo $KC_BOOT_ADMIN` |
| KC_CLIENT_SECRET_* (4 vars) set | `env \| grep KC_CLIENT_SECRET` |
| `jq` installed | `jq --version` |
| `curl` installed | `curl --version` |

---

## GATE-A — Remediate Existing Keycloak (Choose One Option)

**Current state (2026-05-03):** Keycloak 26.2.5 running on evo1:8180, PID 5577,
responding HTTP 500 on all endpoints. I-34 violation: `--db-password` visible in
`ps aux`. Postgres on :15433.

### Option A — Fix Existing KC Process (Recommended)

Stop the broken process, create systemd unit with EnvironmentFile (fixes I-34),
restart:

```bash
# 1. Source secrets
source ~/.banxe/keycloak.env

# 2. Verify env file is mode 600 (I-34)
chmod 600 ~/.banxe/keycloak.env

# 3. Stop existing broken process (PID 5577 or current)
pkill -f 'kc.sh start' || true
sleep 5

# 4. Install systemd unit (wraps KC with EnvironmentFile for I-34 compliance)
source ~/.banxe/keycloak.env
bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/install-systemd-unit.sh

# 5. Start via systemd
systemctl --user enable --now keycloak-banxe-emi

# 6. Verify
systemctl --user status keycloak-banxe-emi
journalctl --user -u keycloak-banxe-emi -n 50 --no-pager
```

Proceed to GATE-B when `healthcheck.sh` passes (see §Health Check below).

### Option B — Start on Alternative Port :8182

If existing KC cannot be repaired without extended downtime:

```bash
# Docker compose on :8182 (does not conflict with PID 5577 on :8180)
cd /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/
source ~/.banxe/keycloak.env

docker compose -f docker-compose.standalone.yml up -d
docker compose -f docker-compose.standalone.yml logs -f keycloak-banxe-emi-standalone
```

Note: Option B requires updating `KC_BASE_URL=http://evo1:8182` in all EMI service configs.

### Option C — Replace Process (Fresh KC on :8180)

```bash
# Kill existing KC
pkill -f 'kc.sh start' || true
sleep 10

# Start Docker KC on :8180 (standard port, no service config changes needed)
cd /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/
source ~/.banxe/keycloak.env

docker compose up -d
docker compose logs -f keycloak-banxe-emi
```

---

## Health Check

Run at any point to verify Keycloak is healthy and realm is accessible:

```bash
# Default: http://evo1:8180
bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/healthcheck.sh

# Custom URL
bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/healthcheck.sh http://evo1:8182
```

Checks performed:
1. `/health/ready` → `{"status": "UP"}`
2. Realm OIDC discovery → issuer matches expected URL
3. Token endpoint returns 401/400 for invalid client (reachable)

---

## GATE-B — Import Realm + Provision Clients

### Step 1: Import Realm (Idempotent)

```bash
source ~/.banxe/keycloak.env
export KC_BASE_URL=http://evo1:8180   # or :8182 if Option B

bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/import-realm.sh
```

Expected output:
```
=== Authenticating with Keycloak admin ===
=== Checking if realm banxe-emi exists ===
=== Importing realm from .../banxe-emi-realm.json ===
Realm banxe-emi imported.
=== Import done. Run provision-clients.sh next (GATE-B). ===
```

If realm already exists: `Realm banxe-emi already exists — skipping import (idempotent)`.

### Step 2: Provision Client Secrets

```bash
source ~/.banxe/keycloak.env
# KC_CLIENT_SECRET_* must be set (see .env.example for variable names)

bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/provision-clients.sh
```

Expected output:
```
=== Authenticating with Keycloak admin ===
=== Provisioning client_secrets for realm banxe-emi ===
--- Provisioning: banxe-compliance-api
PROVISIONED: banxe-compliance-api (uuid=<uuid>)
--- Provisioning: banxe-dashboard
PROVISIONED: banxe-dashboard (uuid=<uuid>)
--- Provisioning: deep-search
PROVISIONED: deep-search (uuid=<uuid>)
--- Provisioning: drive_watcher
PROVISIONED: drive_watcher (uuid=<uuid>)
=== Provision complete. Verify with scripts/healthcheck.sh smoke-test. ===
```

### Step 3: Smoke Test

```bash
source ~/.banxe/keycloak.env

# Full healthcheck
bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/healthcheck.sh

# Token smoke tests for all 4 clients
source /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/examples/get-token.curl.txt
```

All 4 clients must return an access token. Negative test (wrong secret) must return HTTP 401.

---

## Client Registry

| Client ID | EMI Service | Secret Env Var |
|-----------|-------------|----------------|
| `banxe-compliance-api` | banxe-compliance-api | `KC_CLIENT_SECRET_BANXE_COMPLIANCE_API` |
| `banxe-dashboard` | banxe-dashboard | `KC_CLIENT_SECRET_BANXE_DASHBOARD` |
| `deep-search` | deep-search | `KC_CLIENT_SECRET_DEEP_SEARCH` |
| `drive_watcher` | drive_watcher | `KC_CLIENT_SECRET_DRIVE_WATCHER` |

All clients: `client_credentials` grant only, `serviceAccountsEnabled=true`,
no standard/implicit/direct-access flows, `publicClient=false`.

Token claims injected via protocolMappers:
- `service_id` — client ID string
- `environment` — `"prod"`
- `compliance_scope` — `"emi"`
- `roles` — `["service-account"]` (realm role)

Token TTL: 900s (15 min). Refresh not applicable for client_credentials.

---

## GATE-C — Switch EMI Services to OIDC (Requires Explicit Signal)

**DO NOT execute Block K (OIDC service switching) without explicit "go GATE-C" in chat.**

When GATE-C is received, each EMI service will have its auth adapter switched from
the current stub/basic-auth to `KeycloakAdapter` (client_credentials OIDC):

```
services/iam/adapters/keycloak_adapter.py  ← fetches token, caches until exp-60s
services/iam/ports.py                       ← IAMPort Protocol
api/deps.py                                 ← injects KeycloakAdapter when IAM_ADAPTER=keycloak
api/routers/auth.py                         ← validates Bearer token via KC introspect/public_key
```

Environment variable: `IAM_ADAPTER=keycloak` + `KC_BASE_URL=http://evo1:8180`.

---

## GATE-D — Backout / Rollback

**DO NOT execute without explicit "go GATE-L" in chat.**

Rollback sequence (reverse of GATE-C):

```bash
# 1. Set IAM_ADAPTER back to stub (or previous value)
export IAM_ADAPTER=stub

# 2. Restart affected services (one at a time; verify health between each)
# drive_watcher (lowest risk — offline cron)
docker compose restart drive_watcher
bash scripts/healthcheck.sh

# deep-search
docker compose restart deep-search
bash scripts/healthcheck.sh

# banxe-dashboard
docker compose restart banxe-dashboard
bash scripts/healthcheck.sh

# banxe-compliance-api (last — highest risk)
docker compose restart banxe-compliance-api
bash scripts/healthcheck.sh

# 3. Verify no OIDC errors in logs
docker compose logs --tail=100 banxe-compliance-api | grep -i "error\|failed\|keycloak"

# 4. If KC itself must be removed:
systemctl --user stop keycloak-banxe-emi
# OR (Docker KC):
docker compose -f infra/keycloak-banxe-emi/docker-compose.yml down
```

---

## Troubleshooting

### KC returns HTTP 500 on /health/ready

```bash
journalctl --user -u keycloak-banxe-emi -n 100 --no-pager | grep -i "error\|started\|failed"
# Common: database migration failure — check postgres on :15433
psql -h 127.0.0.1 -p 15433 -U keycloak -d keycloak -c "\dt" | head -20
```

### kcadm.sh: "Client not found"

Realm import hasn't run yet. Run `import-realm.sh` first.

### Token returns 401 "Invalid client credentials"

Client secret not provisioned or wrong value. Re-run `provision-clients.sh`.

### Token missing `service_id` claim

ProtocolMapper not applied. Verify `banxe-emi-realm.json` was imported (not a bare realm).
Check: Admin console → Realm banxe-emi → Clients → banxe-compliance-api → Client scopes.

### `ps aux` still shows `--db-password` after systemd install

Process started outside systemd. Kill it: `pkill -f 'kc.sh start'` then
`systemctl --user start keycloak-banxe-emi`.

---

## Tech debt — KC_DB backend

Initial deployment uses `KC_DB=dev-file` (file-backed H2 inside the keycloak_data volume) due to systematic Quarkus build-step kill on evo1 when `kc.sh build` is invoked against `KC_DB=postgres`. Tracked as **G-IAM-09** in GAP-REGISTER. Migration target: 2026-05-31. Production guarantees (audit retention, FCA CASS 15) are unaffected — events stay in keycloak_data volume; backup of /opt/keycloak/data is sufficient.

---

## Evidence Artifacts (GAP-REGISTER Links)

| Gap | Artifact |
|-----|---------|
| G-IAM-01 (realm exists) | `realms/banxe-emi-realm.json` + `import-realm.sh` |
| G-IAM-02 (clients provisioned) | `scripts/provision-clients.sh` |
| G-IAM-04 (healthcheck) | `scripts/healthcheck.sh` |
| G-IAM-05 (smoke test) | `examples/get-token.curl.txt` |
| G-IAM-07 (backout runbook) | This RUNBOOK.md §GATE-D |
| I-34 fix | `scripts/install-systemd-unit.sh` |
| Pre-flight state | `PRECHECK-2026-05-03.md` |

---

## References

- ADR-017: `banxe-architecture/decisions/ADR-017-keycloak-iam.md`
- ADR-022: `docs/adr/ADR-022-emi-service-auth.md`
- GAP-REGISTER: `GAP-REGISTER.md` (G-IAM-01..08)
- Realm JSON spec: [Keycloak 26.2 Realm Export docs](https://www.keycloak.org/docs/latest/server_admin/#admin-cli)
- healthcheck.sh: `scripts/healthcheck.sh`
- provision-clients.sh: `scripts/provision-clients.sh`
