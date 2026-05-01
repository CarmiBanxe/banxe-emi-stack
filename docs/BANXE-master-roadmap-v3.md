# BANXE EMI AI Bank — Master Roadmap v3

**Created:** 2026-04-30
**Sprint deadline:** 2026-05-07 (P0)
**Branch:** sprint4/sca-application-boundary
**Supersedes:** docs/Keycloak-next-session-roadmap.md

---

## Context

### Hardware
- NucBox: Ubuntu 24.04, Linux 6.17.0-22, AMD Ryzen AI MAX+ 395 (Zen 5), 30 GiB RAM
- Legion: Windows + WSL2, dev workstation
- Known bug: HotSpot C2 JIT crash on Zen 5 + kernel 6.17 → workaround `-XX:TieredStopAtLevel=1`

### Service inventory (NucBox)
- 🔴 Crashing 137: `banxe-keycloak` (replaced by host), `midaz-ledger` (CBS), `banxe-frankfurter` (FX)
- 🔴 Crashing uvicorn: `banxe-api.service` (LexisNexis Compliance, 83 restarts/6s)
- ✅ Running: Marble, Jube TM, Ballerine, MiroFish, banxe-mock-aspsp, midaz-rabbitmq/mongo, braslina-db
- ⏳ Installed not running: n8n
- ❌ Exited: HyperSwitch full stack, banxe-postgres, redis, postgres
- ✅ New (current session): host Keycloak 26.2.5 :8180 + nginx /auth/

### AI stack
- Legion: OpenClaw-MOA (9 agents) — **active but cron empty → idle**
- Legion: MetaClaw v0.3.0, MCP :8100, banxe-mcp 7 read-only tools, 4 Claude Code worktrees — setup in progress
- Legion: Claude Code Max + planned DeepSeek via Anthropic endpoint — not configured
- NucBox: OpenClaw self-hosted — **not installed**
- NucBox: n8n — installed not running

### Security rules (immutable)
- OpenClaw version ≥ 2026.1.29 (CVE-2026-25253, RCE via WebSocket)
- Gateway behind VPN only, never public
- QClaw 24h Tencent buffer → NOT for production data
- Production data + credentials → NucBox self-hosted only
- Legion = dev/research/code only, no client data
- Sandbox ephemeral tmpfs on every tool call

### Compliance
- Pre-commit Spec-First Auditor (12 blocks PASS)
- GDPR / FCA / ACPR markers
- Rule: API keys, payment schemas, client data — NEVER in DeepSeek/QClaw

---

## PHASE 1 — P0 Sprint Deadline (Apr 30 → May 7)

### Day 0 — Thu Apr 30 (TODAY)
- [x] 1.1 Remove stale container `banxe-keycloak` (same Zen 5 JIT victim, host running)
- [x] 1.2 Change bootstrap admin/admin → strong password, secrets/keycloak-admin.password chmod 600
- [x] 1.3 Fix `banxe-api.service` (83 restarts/6s) → `journalctl -u banxe-api -n 200`
- [x] 1.4 Finish MetaClaw setup on Legion (agent=openclaw, mode=madmax, URL=http://localhost:3000), `metaclaw start --daemon`
- [x] 1.5 Fix `midaz-ledger` (CBS) → docker logs
- [x] 1.6 Fix `banxe-frankfurter` (FX)
- [x] 1.7 Start n8n on NucBox

### Day 1 — Fri May 1 (Sprint 4 Track A)
- [x] 1.8 Finish `services/auth/sca_service.py` (ScaApplicationService)
- [x] 1.9 pytest for SCA critical paths, commit
- [ ] 1.10 JWT middleware in `banxe-api` via JWKS
- [ ] 1.11 `Depends(get_current_user)` for protected endpoints
- [ ] 1.12 Service-to-service `client_credentials` with `banxe-backend`
- [ ] 1.13 Fill empty cron for 9 OpenClaw-MOA agents (compliance/fx/payments/kyc/risk/analytics/supervisor)

### Days 2-3 — Sat-Sun May 2-3 (Track B Wave 1-2)
- [ ] 1.14 notifications service
- [ ] 1.15 openbanking integrations
- [ ] 1.16 OpenClaw-MOA Skills via MCP banxe-mcp: banxe-fastapi-call, github-actions-watch, docker-monitor, marble-query, jube-score, ballerine-workflow

### Days 4-5 — Mon-Tue May 4-5 (Track B Wave 3-4)
- [ ] 1.17 payments wave
- [ ] 1.18 compliance wave: Marble + Ballerine + Jube via n8n workflow
- [ ] 1.19 Webhook FastAPI → OpenClaw-MOA → reports (KYC daily, AML cron 03:00, reconciliation cron 03:00)

### Day 6 — Wed May 6 (Quality Gates)
- [ ] 1.20 ruff check --fix
- [ ] 1.21 mypy --strict services/
- [ ] 1.22 pytest --cov ≥80% on changed files
- [ ] 1.23 Pre-commit Spec-First Auditor PASS
- [ ] 1.24 Pre-deploy health check via supervisor agent

### Day 7 — Thu May 7 (P0 DEADLINE)
- [ ] 1.25 Sprint 4 closed, FIN060 generated, tag v0.4.0-sprint4

---

## PHASE 2 — Stabilization & Hardening (May 8 → May 21)

### Keycloak hardening
- [ ] 2.1 Permanent admin user in master, delete bootstrap
- [ ] 2.2 KC_HOSTNAME strict on production domain
- [ ] 2.3 SMTP for realm banxe (reset, verify)
- [ ] 2.4 Roles: customer, compliance-officer, admin, support, system
- [ ] 2.5 Password policy (length 12+, history 5, complexity)
- [ ] 2.6 MFA TOTP required for admin/compliance-officer
- [ ] 2.7 Session timeouts: access 15m, refresh 30m, SSO 8h
- [ ] 2.8 Client `banxe-frontend` (public, PKCE)

### Observability
- [ ] 2.9 KC_METRICS_ENABLED=true + Prometheus /auth/metrics
- [ ] 2.10 Centralized logging (loki/elastic)
- [ ] 2.11 Grafana dashboard: 9 agents + BANXE services

### CLAUDE.md
- [ ] 2.12 Section "AI Orchestration Policy"
- [ ] 2.13 Rule: secrets/payment schemas/client data NEVER in cloud LLM
- [ ] 2.14 Pre-commit hook to block API keys / PII commits

### Days 2-3 — Sat-Sun May 2-3 (Track B Wave 1-2)
- [ ] 1.14 notifications service
- [ ] 1.15 openbanking integrations
- [ ] 1.16 OpenClaw-MOA Skills via MCP banxe-mcp: banxe-fastapi-call, github-actions-watch, docker-monitor, marble-query, jube-score, ballerine-workflow

### Days 4-5 — Mon-Tue May 4-5 (Track B Wave 3-4)
- [ ] 1.17 payments wave
- [ ] 1.18 compliance wave: Marble + Ballerine + Jube via n8n workflow
- [ ] 1.19 Webhook FastAPI → OpenClaw-MOA → reports (KYC daily, AML cron 03:00, reconciliation cron 03:00)

### Day 6 — Wed May 6 (Quality Gates)
- [ ] 1.20 ruff check --fix
- [ ] 1.21 mypy --strict services/
- [ ] 1.22 pytest --cov ≥80% on changed files
- [ ] 1.23 Pre-commit Spec-First Auditor PASS
- [ ] 1.24 Pre-deploy health check via supervisor agent

### Day 7 — Thu May 7 (P0 DEADLINE)
- [ ] 1.25 Sprint 4 closed, FIN060 generated, tag v0.4.0-sprint4

### Days 2-3 — Sat-Sun May 2-3 (Track B Wave 1-2)
- [ ] 1.14 notifications service
- [ ] 1.15 openbanking integrations
- [ ] 1.16 OpenClaw-MOA Skills via MCP banxe-mcp: banxe-fastapi-call, github-actions-watch, docker-monitor, marble-query, jube-score, ballerine-workflow

### Days 4-5 — Mon-Tue May 4-5 (Track B Wave 3-4)
- [ ] 1.17 payments wave
- [ ] 1.18 compliance wave: Marble + Ballerine + Jube via n8n workflow
- [ ] 1.19 Webhook FastAPI → OpenClaw-MOA → reports (KYC daily, AML cron 03:00, reconciliation cron 03:00)

### Day 6 — Wed May 6 (Quality Gates)
- [ ] 1.20 ruff check --fix
- [ ] 1.21 mypy --strict services/
- [ ] 1.22 pytest --cov ≥80% on changed files
- [ ] 1.23 Pre-commit Spec-First Auditor PASS
- [ ] 1.24 Pre-deploy health check via supervisor agent

### Day 7 — Thu May 7 (P0 DEADLINE)
- [ ] 1.25 Sprint 4 closed, FIN060 generated, tag v0.4.0-sprint4
