# CLAUDE.md — Banxe AI Bank: EMI Financial Analytics Stack
# FinDev Agent | P0 Execution Repo | Version: 1.0.0
# FCA CASS 15 / PS25/12 | Deadline: 7 May 2026

## ОБЯЗАТЕЛЬНО ПРОЧЕСТЬ ПЕРВЫМ

Это P0 execution repo для финансово-аналитического блока Banxe AI Bank.
**Scope:** только CASS 15 P0 items до 7 May 2026.
**НЕ scope:** AML, KYC, Cards, K8s, полный event streaming.

Главный архитектурный репо: https://github.com/CarmiBanxe/banxe-architecture
Instruction Ledger: banxe-architecture/INSTRUCTION-LEDGER.md
Compliance Matrix: banxe-architecture/docs/COMPLIANCE-MATRIX.md
Research base: banxe-architecture/docs/financial-analytics-research.md

---

## 0. FinDev Agent — Роль и ограничения

**Специализация:** FCA CASS 15 compliance engineering.

**Hard Constraints (НЕЛЬЗЯ):**
1. НИКОГДА float для денег — только `Decimal` (Python) / `Decimal(20,8)` (SQL)
2. НИКОГДА секреты в коде — только `.env` / переменные окружения
3. НИКОГДА технологии из санкционных юрисдикций (РФ, Иран, КНДР, Беларусь, Сирия)
4. ВСЕГДА audit trail — каждое финансовое действие логируется в ClickHouse / pgAudit
5. НИКОГДА платные SaaS без self-hosted альтернативы в production

**Приоритет задач:**
```
P0 (до 7 May 2026):
  1. pgAudit на всех PostgreSQL БД                 ✅ S36
  2. Daily safeguarding reconciliation              ✅ S36
  3. FIN060 generation → RegData                   ✅ S36
  4. Frankfurter FX rates (self-hosted ECB)         ✅ S37
  5. adorsys PSD2 gateway (bank statement polling)  ✅ S37

P1 (Q2-Q3 2026): Metabase/Superset, Great Expectations, Debezium, Temporal, Kafka
P2 (Q4 2026): Camunda 7, OpenMetadata, Airbyte
P3 (Year 2+): FinGPT, OpenBB, Apache Flink
```

---

## 1. EMI BANXE AI BANK — Project Rules

Project: EMI BANXE AI BANK — FCA-authorised fintech EMI platform.
Stack: Python 3.12, FastAPI, PostgreSQL 17, ClickHouse, Redis, Docker, Alembic.

### Development Commands

```bash
# Tests
python -m pytest tests/ -v --tb=short                      # all tests
python -m pytest tests/test_<module>/ -x -q --no-cov       # single module fast
python -m pytest tests/ --cov=services --cov=api --cov-fail-under=80  # with coverage

# Linting
ruff check .                  # lint (must be 0 issues before commit)
ruff format .                 # auto-format
mypy services/ api/           # type checking

# Database
alembic upgrade head          # apply all migrations (ask permission)
alembic downgrade -1          # roll back one (ask permission)
alembic revision --autogenerate -m "description"  # generate migration

# Docker P0 stack
docker compose -f docker/docker-compose.master.yml up -d   # full P0 stack
docker compose -f docker/docker-compose.master.yml down    # stop all
docker compose -f docker/docker-compose.master.yml logs -f api  # stream logs

# Quality gate
bash scripts/quality-gate.sh  # full gate: ruff + mypy + pytest + semgrep
```

### Architecture Rules

- Each service in `services/<domain>/` is an independent unit.
- Never import code directly between services — use API contracts or message queues.
- Protocol DI pattern: Port (Protocol) → Service → Adapter (InMemory/Real).
- All value objects: `@dataclass(frozen=True)` or `Pydantic(frozen=True)`.
- All external dependencies injected via constructor, never module-level singletons.

### Git Conventions

- Branch naming: `feat/*`, `fix/*`, `refactor/*`, `hotfix/*`.
- Never push directly to main (hook enforced).
- All changes through pull requests and code review.
- Commit format: `type(scope): message [IL-XXX]`.

### Security Rules

- Never hardcode secrets, tokens, passwords or keys.
- Always use environment variables via Pydantic Settings.
- Never read `.env` files or `secrets/` without explicit confirmation.
- Blocked jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE/SY (I-02) — enforced in all payment flows.

### Database Rules

- Every schema change requires an Alembic migration file.
- Migrations must be reviewed before applying (`ask` permission level).
- No destructive SQL against production databases without sign-off.
- ClickHouse audit tables: TTL minimum 5 years (I-08), never reduce.

### Code Quality

- `ruff` and `mypy` must pass before any commit is considered ready.
- Tests in pytest, minimum 80% coverage for `services/` and `api/`.
- For every non-trivial business rule change, ensure tests are present.
- I-01: `Decimal` only for monetary values — Semgrep rule `banxe-float-money` enforces this.

### When NOT to Ask for Confirmation

For the following changes, do NOT ask extra clarifying questions beyond permissions rules. Propose a plan, apply it, and show the diff:

**Auto-apply without prompting** (safe, local, reversible):
- Pure refactoring within a single module (no behaviour change, tests stay green)
- Adding or fixing type hints, docstrings, or inline comments
- Changes only inside `tests/` or `services/*/tests/`
- Running allowed tooling: `ruff`, `mypy`, `pytest`, `alembic revision`
- Reading any non-secret file to understand context

**Always present plan and wait for YES** (risky, irreversible, or cross-cutting):
- Any DB schema change or new Alembic migration
- Changes to cross-service interfaces or shared API contracts
- Touching financial invariants (I-01 Decimal, I-02 jurisdictions, I-24 audit, I-27 HITL)
- Production configuration, secrets layout, or environment variables
- `alembic upgrade` / `alembic downgrade` (always `ask`, blocked for `*prod*`)

#### Auto-edit zones

For files under these paths, do NOT ask additional confirmation questions beyond the standard editor prompt — propose a plan, apply edits, and show the diff:

- `scripts/**/*.py`
- `tests/**/*.py`
- `services/*/tests/**/*.py`
- `services/*/schemas/**/*.py`
- `services/*/proto/**/*.py`

For files under these paths, you MUST present a short risk analysis and explicit plan before any edit:

- `alembic/versions/**`
- `services/*/api/**`
- `services/*/contracts/**`
- `infra/**`
- `deploy/**`
- any production configuration files

---

## 2. P0 Stack Map

```
┌──────────────────────────────────────────────────────────────┐
│              BANXE EMI — P0 ANALYTICS STACK                  │
│              FCA CASS 15 | Deadline: 7 May 2026              │
├──────────────────┬───────────────────┬───────────────────────┤
│  LEDGER          │  RECONCILIATION   │  REPORTING            │
├──────────────────┼───────────────────┼───────────────────────┤
│ Midaz :8095      │ Blnk Finance      │ dbt Core              │
│ (PRIMARY CBS)    │ bankstatementparser│ (staging→marts→fin060)│
│ LedgerPort ABC   │ (CAMT.053/MT940)  │ JasperReports /       │
│ create_tx()      │ ReconciliationEng │ WeasyPrint            │
│ get_balance()    │ StatementFetcher  │ → FIN060 PDF          │
│                  │                   │ → RegData upload      │
├──────────────────┼───────────────────┼───────────────────────┤
│  AUDIT TRAIL     │  FX / RATES       │  INFRASTRUCTURE       │
├──────────────────┼───────────────────┼───────────────────────┤
│ pgAudit          │ Frankfurter       │ PostgreSQL 17 :5432   │
│ ClickHouse :9000 │ (self-hosted ECB) │ ClickHouse :9000      │
│ (5yr TTL append) │ 160+ currencies   │ Redis :6379           │
│ safeguarding_    │ No API key needed │ n8n :5678 (workflows) │
│ events table     │                   │                       │
└──────────────────┴───────────────────┴───────────────────────┘
                   adorsys PSD2 Gateway
                   → CAMT.053 bank statement auto-pull
```

---

## 3. Связанные репозитории

| Репо | URL | Назначение |
|------|-----|-----------|
| banxe-architecture | github.com/CarmiBanxe/banxe-architecture | Архитектура, IL, ADR, COMPLIANCE-MATRIX |
| vibe-coding | github.com/CarmiBanxe/vibe-coding | Compliance engine, AML stack, Midaz adapter |
| **banxe-emi-stack** | github.com/CarmiBanxe/banxe-emi-stack | **P0 Financial Analytics (этот репо)** |

---

## 4. Правила git workflow

- main branch protected — только через PR
- Каждый commit = один P0 item
- Commit message: `feat(P0-FA-NN): описание`
- IL update обязателен после каждого шага
