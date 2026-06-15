# Operations Runbook — STRATEGY-B Keycloak Cutover (Legion host)

**Status:** ARCHIVED — production cutover completed 2026-05-04.
**Source of truth:** `infra/keycloak-banxe-emi/RUNBOOK.md` §STRATEGY-B Resolution + §G-IAM-09 Closure.
**This document:** ops-side summary for on-call / handoff. For step-by-step truth, follow source RUNBOOK.

---

## 1. Why STRATEGY-B

evo1 kernel 6.17 + Docker BuildKit triggered systematic Quarkus `kc.sh build` SIGKILL during initial sessions. STRATEGY-A (own Postgres on evo1) and STRATEGY-C (host KC binary on evo1, no root) were rejected. STRATEGY-B (host migration to Legion via Tailscale) succeeded — Legion kernel 6.6 (WSL2) does not exhibit the kill.

## 2. Production state (as of 2026-05-04)

| Property | Value |
|---|---|
| Host | Legion (WSL2 kernel 6.6, host-Windows + Tailscale) |
| URL | `http://100.101.218.26:8180` (Legion Tailscale IP) |
| Realm | `banxe-emi` (sslRequired=none; Tailscale provides mTLS) |
| Backend | dev-file (H2) — production on dev-file as bridge; Postgres backend validated on staging :8181 |
| Clients | `banxe-compliance-api`, `banxe-dashboard`, `deep-search`, `drive_watcher` — all `serviceAccountsEnabled=true`, `publicClient=false`, secrets `chmod 600` in `~/.banxe/keycloak.env` |
| Smoke | client_credentials 4/4 OK; expires_in=900s |
| Tag | `cass15-iam-cutover-2026-05-07` (commit `78b1643` in banxe-emi-stack) |
| PR | banxe-emi-stack #50 (cutover), #55 (Postgres staging), #53 (ROADMAP Phase 57) |

## 3. Networking

evo1 services reach KC via Tailscale mesh:
- `evo1` → `legion` (`100.101.218.26`) on Tailscale; mTLS handled by Tailscale.
- WSL2 NAT IP (`172.22.x.x`) is **not** LAN-reachable; do not use it.
- If Tailscale is down: KC unreachable from evo1. Fallback = restart Tailscale on Legion + verify `tailscale status`.

## 4. Phase F — switch dev-file → Postgres backend (currently STAGED, not in prod)

Trigger: operator says "go G-IAM-09 switch".

Steps (canonical: `infra/keycloak-banxe-emi/RUNBOOK.md §G-IAM-09 Closure`):
1. Source env: `cd ~/keycloak-banxe-emi-legion && set -a && source ~/.banxe/keycloak.env && set +a`
2. Stop dev-file KC: `docker compose down`
3. Add to env: `KC_DB_USER=keycloak`, `KC_DB_PASSWORD=<generated>`, `KC_DB_NAME=keycloak`
4. Pull new compose: `cp /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/docker-compose.yml ./docker-compose.yml`
5. Bring up: `docker compose up -d`
6. Wait healthy: `docker compose ps`
7. Re-patch `sslRequired=NONE` on `banxe-emi` realm (post-import).
8. Re-provision 4 client secrets: `scripts/provision-clients.sh`
9. Update `~/.banxe/keycloak.env` with new `KC_CLIENT_SECRET_*`.
10. Smoke 4/4 client_credentials.
11. Tag `g-iam-09-postgres-backend-closed-<date>`.

Estimated downtime: 30–60s.

## 5. Backout

If Phase F fails:
- `docker compose down -v` (volumes off, including new Postgres data).
- Restore previous compose + env from git history (`git checkout <pre-Phase-F-commit> -- docker-compose.yml`).
- `docker compose up -d` brings dev-file KC back.
- Smoke 4/4. Re-tag.

## 6. Health checks

- `curl http://100.101.218.26:8180/realms/banxe-emi/.well-known/openid-configuration` → 200 OK with `issuer`, `token_endpoint`.
- `client_credentials` test: see `infra/keycloak-banxe-emi/scripts/provision-clients.sh` and tests in `tests/test_keycloak_client_credentials.py`.

## 7. Related artefacts

- ADR-017: `banxe-architecture/decisions/ADR-017-keycloak-iam-cutover.md`
- INVARIANTS: I-34 (no direct credentials in EMI configs), I-35 (Keycloak realm `banxe-emi` as single IAM issuer)
- GAP-REGISTER: G-IAM-08 DONE 2026-05-04 (canonical), G-IAM-09 DONE 2026-05-04 (staging validation)
- HANDOFF: `docs/sessions/HANDOFF-2026-05-04-guardian-canon.md`

---

**V-13 closure:** This file fulfils HANDOFF V-13 ("STRATEGY-B runbook not archived in /docs/ops"). Created 2026-05-05.
