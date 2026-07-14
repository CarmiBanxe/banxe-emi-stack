# Phase-1 Audit — Topology & Dependency Manifests
# DATE: 2026-07-14
# STATUS: DRAFT — Legion/OpenManus code is still evolving; a second finer pass is planned.
# SCOPE: Repository identities · topology summary · dependency manifests · Charter §8 forbidden-dep scan · anomalies.
# NOT IN SCOPE (later passes): runtime entrypoints · safety/compliance surfaces · test harnesses.

---

## 1. Repository Identities

| Field              | banxe-emi-stack                      | Legion / OpenManus                   |
|--------------------|--------------------------------------|--------------------------------------|
| **Host path**      | `/home/mmber/banxe-emi-stack`        | `/home/mmber/OpenManus`              |
| **Working branch** | `fix/ledger-test-env`                | `main`                               |
| **HEAD SHA**       | `31f1cee`                            | `38c0ce6`                            |
| **Backup tag**     | `pre-reconcile/20260714`             | `pre-reconcile/20260714`             |
| **Tag SHA**        | `2acf540`                            | `26ef51a`                            |
| **Role**           | BANXE EMI — FCA P0 analytics stack   | Legion Private Engine (AI/RL)        |

Both backup tags were created at audit entry-point (`2026-07-14`) and are verified present.
Neither repo had tracked-dirty files at snapshot time (both were tracked-clean per `git status --porcelain`).

---

## 2. Topology Summary

### 2.1 banxe-emi-stack

FCA CASS 15 financial analytics platform. FastAPI / Python 3.12 / PostgreSQL 17 / ClickHouse / Redis.

Key top-level directories and governance files:

| Path                          | Purpose                                                      |
|-------------------------------|--------------------------------------------------------------|
| `agents/`                     | Compliance swarm agents (AML, KYC, TM, CDD, fraud)          |
| `api/`                        | FastAPI route handlers and OpenAPI models                    |
| `alembic/`                    | Database migrations (PostgreSQL)                             |
| `ledger/`                     | Core ledger service (Midaz adapter, LedgerPort)              |
| `compliance-experiments/`     | Compliance Experiment Copilot (CEC)                          |
| `docker/`                     | Docker Compose stacks (master + per-service)                 |
| `frontend/`                   | React 19 / TypeScript / Tailwind web app                     |
| `infra/`                      | ClickHouse migrations, PostgreSQL infra, pgAudit config      |
| `docs/`                       | Architecture ADRs, compliance docs, runbooks                 |
| `CANON.md`                    | Governance canon — immutable operating rules                 |
| `INVARIANTS.md`               | Financial invariants registry (I-01 … I-28)                 |
| `INSTRUCTION-LEDGER.md`       | Instruction ledger (IL entries, task tracking)               |
| `GAP-REGISTER.md`             | FCA compliance gap register                                  |

### 2.2 Legion / OpenManus

Private AI/RL engine. PyTorch-based training pipeline, RL agents, monitoring, Docker deployment.

Key top-level directories and notable files:

| Path                          | Purpose                                                      |
|-------------------------------|--------------------------------------------------------------|
| `openmanus_rl/`               | Core RL training modules                                     |
| `docker/`                     | Docker build context and supporting images                   |
| `docker-compose.yml`          | Compose stack for Legion runtime                             |
| `monitoring/`                 | Metrics / observability setup                                |
| `config/`                     | Runtime configuration files                                  |
| `examples/`                   | Usage examples and demo scripts                              |
| `openmanus_integration.py`    | Integration entry point                                      |
| `merge_repositories.py`       | Utility — repository merge / sync tooling                    |
| `Dockerfile`                  | Primary image build definition                               |
| `*_ROADMAP.md`, `*_ANALYSIS.md` | Design documents (multiple: sprint plans, analysis reports)|

---

## 3. Dependency Manifests Inventory

### 3.1 banxe-emi-stack

| File                       | Lines / Count | Notes                                              |
|----------------------------|---------------|----------------------------------------------------|
| `pyproject.toml`           | 131 lines     | Primary Python build + tool config (Ruff, mypy, pytest) |
| `requirements.txt`         | 22 packages   | Core runtime deps (FastAPI, SQLAlchemy, etc.)      |
| `requirements-compliance.txt` | 8 packages | Compliance-specific extras (AML/KYC services)      |
| `package.json`             | (frontend)    | Node/React deps for frontend (Biome, Vite, React 19) |

### 3.2 Legion / OpenManus

| File                          | Lines / Count | Notes                                           |
|-------------------------------|---------------|-------------------------------------------------|
| `pyproject.toml`              | 79 lines      | Python build config; RL / ML tooling           |
| `requirements.txt`            | 28 packages   | Primary runtime deps                            |
| `requirements-legion.txt`     | 25 packages   | Legion-specific extras (RL training stack)      |
| `requirements_docker.txt`     | 16 packages   | Docker image minimal deps                       |

---

## 4. Charter §8 — Forbidden Dependency Scan

**Scan target:** all manifest files in both repos.
**Forbidden patterns (Charter §8):** Tor, onion routing, anonymity proxies, SOCKS proxies, i2p, anonymization layers.

### 4.1 Finding: NO forbidden dependencies detected

Neither repository contains any real match for Charter §8 forbidden patterns.

### 4.2 False Positives (explicitly recorded — do NOT re-flag)

The following strings produced substring hits during automated scanning but are **not** forbidden dependencies. They are recorded here so future auditors do not repeat the false-positive triage:

| String matched | File(s) | Actual package / reason |
|----------------|---------|------------------------|
| `torch`        | Legion manifests, banxe `pyproject.toml` | `torch` = PyTorch ML framework (Meta/Facebook). Not Tor. |
| `torchaudio`   | Legion manifests | PyTorch audio extension. Not Tor. |
| `torchvision`  | Legion manifests | PyTorch vision extension. Not Tor. |
| `torchdata`    | Legion manifests | PyTorch data utilities. Not Tor. |
| `config store` | banxe docs/config context | Generic config storage reference. Not anonymisation. |
| `storybook`    | banxe frontend manifests | UI component development tool. Not anonymisation. |
| Ruff rule codes (e.g. `S310`) | banxe `pyproject.toml` | Ruff linter rule identifiers. Not packages. |

**Verdict: PASS — Charter §8 compliant. Both repos clear.**

---

## 5. Anomalies & Hygiene Notes

### 5.1 Stray file `=2.0` at banxe top-level

A file literally named `=2.0` exists at the top level of `banxe-emi-stack`.

**Root cause (inferred):** unquoted shell invocation such as `pip install pkg>=2.0` without quotes causes the shell to interpret `>=2.0` as a redirection, creating a file named `=2.0`.

**Impact:** non-blocking hygiene issue. No functional impact.

**Action:** recorded here for awareness. **Do NOT delete** — deletion is operator-gated (Charter §4: factory never deletes). Operator should remove this file and verify it is added to `.gitignore` if needed.

### 5.2 Both repos on non-main working branches at snapshot time

| Repo               | Working branch at audit snapshot |
|--------------------|----------------------------------|
| banxe-emi-stack    | `fix/ledger-test-env`            |
| OpenManus          | `main`                           |

banxe-emi-stack is on a feature/fix branch, not `main`. The backup tag `pre-reconcile/20260714` (SHA `2acf540`) points to `31f1cee` on this branch. OpenManus is on `main` (expected). Non-blocking; recorded for completeness.

### 5.3 Untracked root-owned directory

`banxe-emi-stack/docker/docker/clickhouse` is untracked and owned by `root:root`. It is intentionally excluded from all stash operations (no `-u` flag) to avoid requiring `sudo`. Not a manifest concern; recorded for completeness.

---

## 6. Next Steps — NOT YET AUDITED

The following audit dimensions are deferred to later passes. They are explicitly marked as **NOT DONE** in this draft:

| Audit dimension              | Status    | Notes                                                        |
|------------------------------|-----------|--------------------------------------------------------------|
| Runtime entrypoints          | NOT DONE  | FastAPI `main.py`, Legion `openmanus_integration.py`, etc.   |
| Safety / compliance surfaces | NOT DONE  | AML flows, KYC checks, safeguarding reconciliation engine    |
| Test harnesses               | NOT DONE  | pytest suites (banxe: ~1900+ tests), Legion test coverage    |
| Docker image provenance      | NOT DONE  | Base images, layer audit, no sanctioned-jurisdiction sources |
| Secrets / env hygiene        | NOT DONE  | `.env.example` review, no real secrets in repo               |
| API contract surfaces        | NOT DONE  | OpenAPI schema, MCP tool registry (34 tools)                 |
| Inter-repo integration       | NOT DONE  | `merge_repositories.py` in Legion — intent and safety review |

---

## Draft Status Notice

**This document is a DRAFT.**

A second, finer audit pass is planned once the Legion/OpenManus engine stabilises (it is actively evolving). The findings in this document reflect the state at `2026-07-14 01:21 UTC` (backup tag `pre-reconcile/20260714`). All facts herein are ground-truth from verified read-only shell output at that timestamp.

Do not treat this document as a final compliance artefact. It serves as the baseline snapshot for subsequent reconciliation phases.

---

*Generated by BANXE Factory Agent | Reconciliation Bootstrap v2 | Phase-1 Audit pass*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
