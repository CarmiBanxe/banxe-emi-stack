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

## Enforcement artefacts

| Artefact | Path | Covers |
|----------|------|--------|
| Semgrep rules | `.semgrep/banxe-rules.yml` | I-01, I-08, I-24 |
| AML thresholds | `services/aml/aml_thresholds.py` | I-02, I-03, I-04 |
| Pydantic validators | `api/models/` | I-05 |
| HITL service | `services/hitl/feedback_loop.py` | I-27 |
| AI routing policy | `banxe-infra/ai-routing/policy.yaml` | INV-AI-01 |
| pre-commit hooks | `.pre-commit-config.yaml` | INV-AI-01, I-01 |

## References

- Financial invariant rules: `.claude/rules/financial-invariants.md`
- ADR-021 (AI plane): `docs/adr/ADR-021-ai-plane-pii-aml-routing.md`
- AI-PLUMBING.md (LiteLLM aliases + deny-paths): `docs/AI-PLUMBING.md`
- Security policy: `.claude/rules/security-policy.md`
