# GAP-REGISTER — Banxe EMI Stack

> Реестр архитектурных и операционных пробелов (gaps).
> Источник правды по канону: `banxe-architecture/GAP-REGISTER.md`.
> Этот файл — зеркало EMI-стека; в случае расхождения преобладает
> запись в `banxe-architecture`.

**Last updated:** 2026-05-03

---

## Severity legend

- **P0** — security / regulatory breach risk
- **P1** — architecture invariant breach
- **P2** — quality / maintainability
- **P3** — nice-to-have

---

## Closed

### 2026-05-03 — ADR-021 rollout

| Gap ID   | Title                                              | Severity | Resolution |
|----------|----------------------------------------------------|----------|------------|
| G-AI-01  | No unified AI entrypoint for EMI services          | P1       | Closed by ADR-021 + INV-AI-01. LiteLLM v2 router (`http://legion:4000/v1`) — единая точка входа. |
| G-AI-02  | Backing-model coupling in service code             | P2       | Closed by ADR-021 alias contract (`ai`, `ai-heavy`, `glm-air`, `reasoning`, `banxe-general`, `fast`, `coding`). |
| G-PII-01 | Risk of PII leak to cloud LLM                      | P0       | Closed by INV-PII-01 + `banxe-infra/ai-routing/policy.yaml` deny-paths. |
| G-PII-02 | No enforcement on deny-paths                       | P0       | Closed by pre-commit hook + review checklist + LiteLLM runtime guard. |
| G-MIG-01 | Legion → evo1 migration without rollback contract  | P1       | Closed by ADR-021 §5: dual-stack until verified PASS; Legion `--user` units сохраняются. |

---

## Open

### Open / 2026-05-03 — ADR-022 IAM cutover (mirror of canonical G-IAM-*)

| Gap ID | Title | Severity | Owner | Target | Notes |
|--------|-------|----------|-------|--------|-------|
| G-IAM-01 | Keycloak realm `banxe-emi` deployed on evo1 (:8180) | P0 | Architecture WG / IAM lead | 2026-05-07 | mirror of canonical G-IAM-01 |
| G-IAM-02 | OIDC discovery URL reachable from EMI services | P0 | IAM lead | 2026-05-07 | mirror of canonical G-IAM-02 |
| G-IAM-03 | Service-to-service tokens for compliance-api, dashboard, deep-search, drive_watcher | P0 | IAM lead | 2026-05-07 | mirror of canonical G-IAM-03 |
| G-IAM-04 | Realm mappers + audit log retention ≥ 12 months | P0 | IAM lead | 2026-05-07 | mirror of canonical G-IAM-04 |
| G-IAM-05 | client_secret rotation policy (90 days / on-incident) | P1 | IAM lead | 2026-05-07 | mirror of canonical G-IAM-05 |
| G-IAM-06 | pre-commit hook + Gitleaks rule blocking direct credentials | P0 | DevOps | 2026-05-07 | mirror of canonical G-IAM-06 |
| G-IAM-07 | Backout procedure verified | P1 | IAM lead | 2026-05-07 | mirror of canonical G-IAM-07 |
| G-IAM-08 | Decommission Legion local IAM after PASS + 7d hold | P2 | IAM lead | 2026-05-14 | BLOCKED_BY G-IAM-01..07 |

---

## Process

1. New gaps go to **Open** with severity, owner, target date.
2. On resolution — move to **Closed** with date-section header and resolution reference (ADR / commit / PR).
3. P0/P1 closures MUST link to an ADR or invariant in `INVARIANTS.md`.
