# GAP-REGISTER — Banxe EMI Stack

> Реестр архитектурных и операционных пробелов (gaps).
> Источник правды по канону: `banxe-architecture/GAP-REGISTER.md`.
> Этот файл — зеркало EMI-стека; в случае расхождения преобладает
> запись в `banxe-architecture`.

**Last updated:** 2026-06-27

---

## Status Reconciliation — 2026-06-27

Per FULL-PROJECT-INSTALLATION-AUDIT-2026-06-21: ~76% L2-complete. All previously-OPEN code GAPs have implementing services installed. Status updates in this document reflect audit findings.

Remaining work: L3-docs/recon-thin + external owner debts (BT-010 FCA RegData key, ufw/Tailscale ACL, ss1 CNIL, bus-factor, product C-02.1/C-37.3) — NOT code gaps.

This session (2026-06-27): GAP-087 safeguarding LIVE (recon Result=success), GAP-088 BT-010 FCA key pending, GAP-089 crypto-ledger Wave E deferred.

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

### 2026-05-03 — ADR-022 rollout (IAM credentials guard)

| Gap ID   | Title                                              | Severity | Resolution |
|----------|----------------------------------------------------|----------|------------|
| G-IAM-06 | pre-commit hook + Semgrep rule blocking direct credentials | P0 | Closed by `feat/iam-creds-guard`: `.semgrep/banxe-rules/iam-no-direct-creds.yml` + pre-commit hook `iam-no-direct-creds` (INV-IAM-01). See `docs/CONTRIBUTING.md §IAM Credentials Guard`. |

---

## Open

### Open / 2026-05-03 — ADR-022 IAM cutover (mirror of canonical G-IAM-*)

| Gap ID | Title | Severity | Owner | Target | Notes |
|--------|-------|----------|-------|--------|-------|
| G-IAM-01 | Keycloak realm `banxe-emi` deployed on evo1 (:8180) | P0 | Architecture WG / IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/` — `realms/banxe-emi-realm.json` + `scripts/import-realm.sh` (WAITING_FOR_GATE-A) | DONE 2026-05-04 via PR #50 (STRATEGY-B Legion deploy) |
| G-IAM-02 | OIDC discovery URL reachable from EMI services | P0 | IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/` — `scripts/healthcheck.sh` + `RUNBOOK.md` §Health Check (WAITING_FOR_GATE-A) | DONE 2026-05-04 via PR #50 (cross-host smoke 4/4 OK) |
| G-IAM-03 | Service-to-service tokens for compliance-api, dashboard, deep-search, drive_watcher | P0 | IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/scripts/provision-clients.sh` + `examples/get-token.curl.txt` (WAITING_FOR_GATE-B) | DONE 2026-05-04 via PR #50 (4 service_credentials tokens issued) |
| G-IAM-04 | Realm mappers + audit log retention ≥ 12 months | P0 | IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/realms/banxe-emi-realm.json` — eventsExpiration=31536000, protocolMappers for service_id/environment/compliance_scope (WAITING_FOR_GATE-A) | DONE 2026-05-04 via PR #50 (realm has protocolMappers + eventsExpiration=31536000) |
| G-IAM-05 | client_secret rotation policy (90 days / on-incident) | P1 | IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/scripts/provision-clients.sh` (re-runnable for rotation), `infra/keycloak-banxe-emi/.env.example` (WAITING_FOR_GATE-B) |
| G-IAM-06 | pre-commit hook + Semgrep rule blocking direct credentials | P0 | DevOps | 2026-05-07 | **DONE 2026-05-03** — `feat/iam-creds-guard`: `.semgrep/banxe-rules/iam-no-direct-creds.yml` + pre-commit hook `iam-no-direct-creds` + `docs/CONTRIBUTING.md` |
| G-IAM-07 | Backout procedure verified | P1 | IAM lead | 2026-05-07 | prep artefacts: `infra/keycloak-banxe-emi/RUNBOOK.md` §GATE-D Backout (WAITING_FOR_GATE-L) | DONE 2026-05-04 via PR #50 (RUNBOOK §GATE-D backout documented) |
| G-IAM-08 | Keycloak realm cutover — DONE via STRATEGY-B (Legion) | P0 | DONE 2026-05-04 |
| G-IAM-99 | EXTERNAL blockers — RESOLVED via STRATEGY-B host migration | P0 | RESOLVED 2026-05-04 |

### Open / 2026-06-27 — S-PROD-2 FCA RegData Reporting (mirror of canonical G-FINRPT-*)

| Gap ID | Title | Severity | Owner | Target | Notes |
|--------|-------|----------|-------|--------|-------|
| GAP-088 | BT-010 — FCA RegData API key + FCA_FRN + API spec | P0 | CEO/CFO | TBD | FCA CASS 15.12.4R — monthly FIN060 submission by 15th. LiveRegDataClient.submit() fail-closed pending BT-010. Draft mode (FIN060 PDF generation, CFO offline review) works. Code-complete via `feat/gap088-regdata-fail-closed` with typed `RegDataNotConfiguredError` exception. Code: `services/reporting/regdata_return.py:175–188` (RegDataNotConfiguredError, fail-closed pending BT-010). → See: [docs/L3-BOUNDARY-REGISTER.md#pending-bt-blockers](docs/L3-BOUNDARY-REGISTER.md#pending-bt-blockers) |
| GAP-089 | Crypto-ledger Midaz production adapter wiring (Wave E) | P3 | CTIO/future team | TBD | S-PROD-3 scope: D-gl (fiat double-entry GL) = DONE (2026-06-20, banxe-emi-stack/services/ledger/); D-crypto deferred to Wave E. Crypto ledger port frozen (PORT-CONTRACTS-FREEZE-2026-05-08, ADR-031 + ADR-025 §15-16). `services/ledger/production/midaz_crypto_stub.py` raises `NotImplementedError` on all network methods (get_balance, create_wallet_address, create_tx, get_fee_estimate, health) with explicit Wave E deferral note in module docstring. Not a P0/P1 blocker for fiat core banking. Implement in dedicated production PR tagged [IL-CRYPTO-PROD-01]. → See: [docs/L3-BOUNDARY-REGISTER.md#boundary-registry](docs/L3-BOUNDARY-REGISTER.md#boundary-registry) (entries 1–9) |

---

## Process

1. New gaps go to **Open** with severity, owner, target date.
2. On resolution — move to **Closed** with date-section header and resolution reference (ADR / commit / PR).
3. P0/P1 closures MUST link to an ADR or invariant in `INVARIANTS.md`.
