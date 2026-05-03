# INVARIANTS — Banxe EMI Stack

> Binding architectural and financial rules. Every invariant is enforced by automated
> tooling and/or code review. Violation severity is stated per entry.
> Source of truth for CLAUDE.md, Semgrep rules, and pre-commit hooks.

**Last updated:** 2026-05-03

---

## Financial invariants

| ID | Rule | Enforcement | Severity |
|----|------|-------------|----------|
| I-01 | No `float` for money — only `Decimal` (Python) / `Decimal(20,8)` (SQL) | Semgrep `banxe-float-money`, Ruff | P0 |
| I-02 | Hard-block jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE/SY | `services/aml/aml_thresholds.py` | P0 |
| I-03 | FATF greylist → EDD (23 countries) | `services/aml/aml_thresholds.py` | P0 |
| I-04 | EDD threshold £10k (individual), £50k (corporate) | `services/aml/aml_thresholds.py` | P0 |
| I-05 | Decimal strings in API responses — never bare `float`/`number` | Pydantic validators in `api/models/` | P0 |
| I-08 | ClickHouse TTL ≥ 5 years (FCA retention) | Semgrep `banxe-clickhouse-ttl-reduce` | P0 |
| I-24 | AuditPort is append-only — no UPDATE/DELETE on audit tables | Semgrep `banxe-audit-delete` | P0 |
| I-27 | HITL: AI PROPOSES only, never auto-applies financial decisions | `services/hitl/feedback_loop.py` | P0 |
| I-28 | Execution discipline: QRAA + IL ledger after every P0 step | CLAUDE.md session protocol | P1 |

---

## AI plane invariants

### INV-AI-01 — No direct cloud LLM calls from EMI services

- **Status:** Binding
- **Date:** 2026-05-03
- **Source:** ADR-021
- **Scope:** banxe-emi-stack, banxe-compliance-api, banxe-dashboard,
  deep-search, drive_watcher, all future EMI services

EMI-сервисы НЕ ВПРАВЕ обращаться напрямую к внешним LLM-провайдерам
(Claude, Gemini, Groq, OpenAI и т. п.). Все AI-вызовы идут через
LiteLLM v2 router (`http://legion:4000/v1`, далее evo1) по
утверждённым алиасам: `ai`, `ai-heavy`, `glm-air`, `reasoning`,
`banxe-general`, `fast`, `coding`.

**Enforcement:** pre-commit hook + code review checklist в каждом
EMI-репо. Backing-модели — деталь реализации plane.

**Violation severity:** P1 (architecture invariant breach).

---

## IAM invariants

### INV-IAM-01 — No Direct Credentials in EMI Service Configs

- **Status:** Binding
- **Date:** 2026-05-03
- **Source:** ADR-022 (mirror of ADR-017); canonical: I-34 (`banxe-architecture/INVARIANTS.md`)
- **Scope:** все EMI-сервисы

EMI-сервисы НЕ ВПРАВЕ хранить direct user/password или статические API-секреты в файлах окружения и конфигурации (`.env*`, `*.yaml`, `*.json`, `docker-compose*`). Любые credentials выдаются только через Keycloak realm `banxe-emi` (см. INV-IAM-02). Master-секреты — operator-supplied env, никогда не коммитятся.

**Enforcement:** pre-commit hook в репо, review checklist, Gitleaks в CI.
**Violation severity:** P0 — security incident (FCA CASS 15 + GDPR Art. 32).

---

### INV-IAM-02 — Keycloak Realm `banxe-emi` as Single IAM Issuer

- **Status:** Binding
- **Date:** 2026-05-03
- **Source:** ADR-022 (mirror of ADR-017); canonical: I-35 (`banxe-architecture/INVARIANTS.md`)
- **Scope:** все EMI-сервисы

Все EMI-сервисы аутентифицируются и авторизуются ИСКЛЮЧИТЕЛЬНО через Keycloak realm `banxe-emi` (`http://evo1:8180/realms/banxe-emi/.well-known/openid-configuration`). Альтернативные IAM-источники (локальный Legion `--user` IAM, hardcoded JWT, статические API-ключи, сторонние OAuth-провайдеры) запрещены для production EMI-флоу. Legion local IAM сохраняется как rollback до подтверждённого PASS на evo1, после чего декомиссионируется (см. ADR-022 §6).

**Enforcement:** review checklist, Keycloak audit log (retention ≥ 12 месяцев), runtime guard в API gateway.
**Violation severity:** P1 — architecture invariant breach. P0 если приводит к утечке клиентских данных.

---

## Enforcement artefacts

| Artefact | Path | Covers |
|----------|------|--------|
| Semgrep rules | `.semgrep/banxe-rules.yml` | I-01, I-08, I-24 |
| Semgrep IAM rule | `.semgrep/banxe-rules/iam-no-direct-creds.yml` | INV-IAM-01 |
| AML thresholds | `services/aml/aml_thresholds.py` | I-02, I-03, I-04 |
| Pydantic validators | `api/models/` | I-05 |
| HITL service | `services/hitl/feedback_loop.py` | I-27 |
| AI routing policy | `banxe-infra/ai-routing/policy.yaml` | INV-AI-01 |
| pre-commit hooks | `.pre-commit-config.yaml` | INV-AI-01, INV-IAM-01, I-01 |

## References

- Financial invariant rules: `.claude/rules/financial-invariants.md`
- ADR-021 (AI plane): `docs/adr/ADR-021-ai-plane-pii-aml-routing.md`
- ADR-022 (IAM cutover mirror): `docs/adr/ADR-022-keycloak-iam-cutover.md`
- AI-PLUMBING.md (LiteLLM aliases + deny-paths): `docs/AI-PLUMBING.md`
- Security policy: `.claude/rules/security-policy.md`
