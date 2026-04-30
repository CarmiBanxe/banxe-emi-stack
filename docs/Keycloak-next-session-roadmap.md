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

