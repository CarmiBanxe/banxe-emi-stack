# Keycloak — Next Session Roadmap

**Created:** 2026-04-30
**Previous session:** Keycloak deployed on NucBox, runbook in `docs/Keycloak-on-NucBox-action-plan.md`, commit `e0ef08d`.
**Branch:** sprint4/sca-application-boundary

---

## Current State (входная точка)

- Keycloak 26.2.5 на NucBox, systemd-сервис `keycloak.service`, auto-start
- URL: `https://192.168.0.72/auth/` (через nginx)
- Realm: `master` (admin/admin — bootstrap, ДОЛЖЕН быть сменён)
- Realm: `banxe` (пустой, без ролей и пользователей)
- Client: `banxe-backend` (confidential), secret в `secrets/banxe-backend.secret`
- JVM workaround: `-XX:TieredStopAtLevel=1` (C2 JIT bug на Zen 5 + ядро 6.17)

---

## Roadmap (по порядку)

### 1. Security hardening (BLOCKER, делаем первым)
- [ ] Сменить bootstrap пароль admin/admin
- [ ] Создать отдельного admin-юзера в realm `master`
- [ ] Удалить временного bootstrap admin
- [ ] Проверить `KC_HOSTNAME` (сейчас `--hostname-strict=false`)
- [ ] Зафиксировать nginx как единственный entrypoint (firewall на 8180)
- [ ] Настроить SMTP для realm `banxe` (password reset, email verification)

### 2. Realm `banxe` — наполнение
- [ ] Роли: `customer`, `compliance-officer`, `admin`, `support`, `system`
- [ ] Password policy (length 12+, history 5, complexity)
- [ ] MFA (TOTP) required для ролей `admin`, `compliance-officer`
- [ ] Session timeouts: access 15m, refresh 30m, SSO 8h
- [ ] Identity providers (опционально: Google/GitHub для staff)

### 3. Backend integration (banxe-api / FastAPI)
- [ ] Установить `python-jose[cryptography]` или `authlib`
- [ ] Middleware для проверки JWT (audience, issuer, exp)
- [ ] JWKS endpoint: `https://192.168.0.72/auth/realms/banxe/protocol/openid-connect/certs`
- [ ] `Depends(get_current_user)` для защищённых endpoints
- [ ] Service-to-service через `client_credentials` flow с `banxe-backend`
- [ ] Тесты: pytest fixtures для замоканного токена

### 4. Frontend integration (OpenClaw / React)
- [ ] Создать client `banxe-frontend` (public, PKCE)
- [ ] Подключить `keycloak-js` или `oidc-client-ts`
- [ ] Redirect URIs для prod-домена
- [ ] Silent token refresh
- [ ] Logout flow

### 5. Observability
- [ ] `KC_METRICS_ENABLED=true` в systemd unit
- [ ] Prometheus scrape `/auth/metrics`
- [ ] Логи `journalctl -u keycloak.service` → центральный лог-стек

### 6. Followup на JVM-баг
- [ ] Открыть issue в Adoptium repo (Temurin 21 C2 crash on Zen 5)
- [ ] Открыть kernel bug report (silent SIGKILL без dmesg на 6.17)
- [ ] При выходе Temurin 21.0.12+ — попробовать снять `-XX:TieredStopAtLevel=1`

---

## Start point of next session
**Шаг 1.1:** сменить bootstrap admin/admin через Admin REST API.


---

### IAM cutover plan v0.1

> **Status: paper-only — NOT for execution until P3.4 migration is PASS**
> All items below are planning artefacts only. No changes to running services.

#### Step 1 — Realm + clients setup
- [ ] Create realm `banxe` (if not exists) with display name "Banxe EMI"
- [ ] Create client `banxe-backend` (confidential, client_credentials grant)
- [ ] Create client `banxe-frontend` (public, PKCE, authorization_code)
- [ ] Create client `banxe-compliance-api` (confidential, service account)
- [ ] Set session timeouts: access_token 15m, refresh_token 30m, SSO session 8h

#### Step 2 — OIDC discovery URL
- Keycloak OIDC discovery: `https://<evo1-host>/auth/realms/banxe/.well-known/openid-configuration`
- JWKS endpoint: `https://<evo1-host>/auth/realms/banxe/protocol/openid-connect/certs`
- Token endpoint: `https://<evo1-host>/auth/realms/banxe/protocol/openid-connect/token`
- **Placeholder:** evo1 host TBD — fill once evo1 migration is PASS

#### Step 3 — Mappers
- [ ] `sub` claim → internal user UUID
- [ ] `email` claim → verified email address
- [ ] `banxe-role` claim → custom mapper from client role `banxe-backend/roles`
- [ ] `preferred_username` → username (not used as authentication identifier)

#### Step 4 — Service-to-service tokens (banxe-compliance-api)
- [ ] Grant `banxe-compliance-api` service account role `compliance-officer`
- [ ] Token flow: `client_credentials`, scope `openid`
- [ ] Inject `KEYCLOAK_CLIENT_ID` + `KEYCLOAK_CLIENT_SECRET` via operator env (never in repo)
- [ ] Validate JWT in FastAPI middleware: audience=`banxe-backend`, issuer=discovery URL

#### Step 5 — evo1 host wiring
- [ ] Keycloak runs in Docker container on evo1 (P4.x placeholder — not started)
- [ ] nginx reverse proxy on evo1: `/auth/` → `localhost:8180`
- [ ] Firewall: port 8180 NOT exposed to public; only nginx egress on 443
- [ ] Health check gate: `GET /auth/realms/banxe` → 200 OK before any cutover step

#### Notes
- All items unchecked — execution blocked on P3.4 evo1 migration PASS
- Do NOT rotate `banxe-backend` secret until migration is confirmed live on evo1
- This plan supersedes items 2.1–2.8 in PHASE 2 of BANXE-master-roadmap-v3.md
