# Session Handoff — 2026-05-04 → next session

## Контекст для следующей сессии

Эта сессия началась 3 May 2026 как `banxe-emi-stack (FCA / KYC / Keycloak roadmaps)` и завершила полный P0 для FCA CASS 15 deadline 2026-05-07. Следующая сессия должна продолжить с **Guardian-shim усиления + conversation-level canon enforcement**.

## Состояние production stack (main HEAD = ee4e0d7)

### Что закрыто этой сессией
- **PR #50** merged — Keycloak realm `banxe-emi` cutover via STRATEGY-B (Legion host migration). Tag `cass15-iam-cutover-2026-05-07`.
- **PR #52** merged — GAP-REGISTER finalised G-IAM-01..05, 07 как DONE.
- **PR #53** merged — ROADMAP Phase 57 records the cutover.
- **PR #55** merged — G-IAM-09 closure (Postgres backend production compose ready, validated 4/4 on staging port 8181).

### Что закрыто как obsolete
- PR #46, #45, #20, #51, #54 — closed с подробными comment'ами.

### Live state
- Production KC: `keycloak-banxe-emi` UP on Legion `100.101.218.26:8180`, dev-file backend, 4 client secrets in `~/.banxe/keycloak.env`.
- Staging KC (Postgres validation): `keycloak-banxe-emi-pg-test` UP on Legion `:8181`, Postgres backend, 4/4 client_credentials grants OK.
- Production main компонент готов к Phase F (live switch на Postgres) — требует operator "go Phase F".

### Открытые задачи (НЕ блокеры 7 May)
- **Phase F** — live switch dev-file → Postgres backend. 30-60s downtime KC. Backout в RUNBOOK.
- **G-IAM-05** — secret rotation 90d (P1 process discipline, не код).
- **PR #36** — factory P1 onboarding (отдельный эпик, не наш).

## Текущий backlog (open PRs)

После cleanup в этой сессии открыт только:
- **PR #36** factory P1 onboarding (`factory/ai-onboarding`, открыт 2026-05-03, 1 CI failure) — отдельный эпик.

## Tag history

- `cass15-iam-cutover-2026-05-07` — official CASS 15 IAM cutover milestone (от 2026-05-04).
- `phase6-validated`, `pre-migration-2026-04-10` — pre-existing.


## Roadmap — следующие шаги (Phase 58+)

| # | Task | Priority | Target |
|---|------|----------|--------|
| 1 | Guardian-shim усиление (conversation-level canon enforcement) | P0 | 2026-05-07 |
| 2 | Оставшиеся GAP items G-IAM-06, G-IAM-08 closure | P0 | 2026-05-07 |
| 3 | FCA CASS 15 deadline smoke tests + sign-off | P0 | 2026-05-07 |
| 4 | Keycloak realm prod health check post-cutover | P1 | 2026-05-08 |
| 5 | ROADMAP Phase 58 planning | P1 | 2026-05-09 |

## 13 Outstanding Violations

| ID | Component | Description | Severity | Status |
|----|-----------|-------------|----------|--------|
| V-01 | Guardian-shim | Canon enforcement not applied at conversation level | CRITICAL | OPEN |
| V-02 | Keycloak | Session timeout misconfigured post-cutover | HIGH | OPEN |
| V-03 | KYC | Missing re-verification trigger on role change | HIGH | OPEN |
| V-04 | IAM | G-IAM-06 not yet closed | HIGH | OPEN |
| V-05 | IAM | G-IAM-08 not yet closed | HIGH | OPEN |
| V-06 | CASS | Reconciliation audit log gaps | HIGH | OPEN |
| V-07 | Postgres | Backup rotation not validated post-migration | MEDIUM | OPEN |
| V-08 | CI/CD | Missing smoke test gate in deploy pipeline | MEDIUM | OPEN |
| V-09 | Secrets | Vault lease renewal not automated | MEDIUM | OPEN |
| V-10 | Monitoring | Keycloak realm alerts not wired to PagerDuty | MEDIUM | OPEN |
| V-11 | KYC | SumSub webhook retry policy undefined | MEDIUM | OPEN |
| V-12 | API Gateway | Rate limits not enforced on /auth/* | LOW | OPEN |
| V-13 | Docs | STRATEGY-B runbook not archived in /docs/ops | LOW | OPEN |

