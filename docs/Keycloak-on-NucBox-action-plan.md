# Keycloak on NucBox — Final Working Configuration

**Date:** 2026-04-30
**Host:** banxe-NucBox-EVO-X2 (AMD Ryzen AI MAX+ 395, Linux 6.17.0-22-generic, Ubuntu 24.04.4)
**Status:** ✅ Production running

---

## 1. Root Cause (что нас мучило)

`Killed` / `exit 137` при любом старте Keycloak (через kc.sh, через Docker, после ребутов).
Перебранные и **опровергнутые** гипотезы:

- Docker / seccomp / cgroup limits
- systemd-oomd
- THP / hugepages / max_map_count
- Hardware MCE
- Memory pressure (memory.events: oom=0, oom_kill=0)
- AVX-512 intrinsics (`-XX:UseAVX=2` не помог)

**Подтверждённый root cause:**
**HotSpot C2 JIT в Temurin 21 (проверено на 21.0.7 и 21.0.11) генерирует невалидный машинный код для AMD Zen 5 (Ryzen AI MAX+ 395) на ядре Linux 6.17.0-22.**
Kernel убивает процесс через SIGKILL (#UD invalid opcode) **без записи в dmesg**.
JDK 17 не использует эти оптимизации — работает.
Лечение: `-XX:TieredStopAtLevel=1` (только C1, без C2).

---

## 2. Working Configuration

### JDK
- Temurin 21.0.11+10, в `/home/banxe/jdk21-full`

### PostgreSQL
- Контейнер `banxe-marble-postgres` (PG 17), `127.0.0.1:15433`
- Role: `keycloak` / Password: `kc_banxe_2026_secure`
- Database: `keycloak` (owner = keycloak)

### Keycloak
- Version: 26.2.5
- Path: `/home/banxe/keycloak-26.2.5`
- Port: 8180 (HTTP, за nginx)
- Bootstrap admin: `admin` / `admin` (СМЕНИТЬ через UI!)

### systemd unit
`/etc/systemd/system/keycloak.service` — enabled, auto-start.
Ключевые env:
- `JAVA_TOOL_OPTIONS=-XX:TieredStopAtLevel=1` ← КРИТИЧНО
- `JAVA_HOME=/home/banxe/jdk21-full`

### nginx reverse proxy
- Sites-enabled: `/etc/nginx/sites-enabled/openclaw`
- Public URL: `https://<host>/auth/`
- HTTP Basic Auth выключен для `/auth/` (`auth_basic off`)

### Realm `banxe`
- displayName: "Banxe AI Bank"
- sslRequired: external, bruteForceProtected: true
- loginWithEmailAllowed: true

### Client `banxe-backend`
- UUID: `85c88521-94cb-4a2f-bbb6-6e6039e8a631`
- Secret: см. `~/banxe-backend.secret` (chmod 600)
- Flows: standard + directAccessGrants + serviceAccounts
- redirectUris: `https://*/auth/*`, `http://localhost/*`

---

## 3. Operations Cheatsheet

```bash
# Status
sudo systemctl status keycloak.service
journalctl -u keycloak.service -f

# Restart
sudo systemctl restart keycloak.service

# Health
curl -sk https://localhost/auth/realms/master | head -c 200
curl -sk https://localhost/auth/realms/banxe   | head -c 200

# Get admin token
TOKEN=$(curl -sk -X POST https://localhost/auth/realms/master/protocol/openid-connect/token \
  -d 'username=admin' -d 'password=admin' \
  -d 'grant_type=password' -d 'client_id=admin-cli' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
```

---

## 4. TODO (на тебе)

1. Сменить пароль admin через UI: `https://192.168.0.72/auth/admin/`
2. Открыть баг-репорты:
   - Adoptium Temurin 21.0.11 — C2 JIT crash on Zen 5
   - kernel.org — silent SIGKILL без dmesg trace на 6.17
3. Когда выйдет fix в Temurin 21.0.12+, убрать `-XX:TieredStopAtLevel=1` из юнита

