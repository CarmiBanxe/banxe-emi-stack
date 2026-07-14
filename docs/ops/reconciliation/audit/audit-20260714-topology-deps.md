# Phase-1 Audit — Topology & Dependency Manifests
# DATE: 2026-07-14
# STATUS: DRAFT — Legion/OpenManus code is still evolving; a second finer pass is planned.
# SCOPE: Repository identities · topology summary · dependency manifests · Charter §8 forbidden-dep scan · anomalies.
# PARTIAL DRAFT (2026-07-15): runtime entrypoints added as §7 — banxe scan INDICATIVE-ONLY (worktree noise).
# NOT IN SCOPE (later passes): safety/compliance surfaces · test harnesses.

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
| Runtime entrypoints          | DONE (DRAFT) | See §7. Legion: verified. Banxe: indicative-only (worktree noise — clean pass needed). |
| Safety / compliance surfaces | NOT DONE  | AML flows, KYC checks, safeguarding reconciliation engine    |
| Test harnesses               | NOT DONE  | pytest suites (banxe: ~1900+ tests), Legion test coverage    |
| Docker image provenance      | NOT DONE  | Base images, layer audit, no sanctioned-jurisdiction sources |
| Secrets / env hygiene        | NOT DONE  | `.env.example` review, no real secrets in repo               |
| API contract surfaces        | NOT DONE  | OpenAPI schema, MCP tool registry (34 tools)                 |
| Inter-repo integration       | NOT DONE  | `merge_repositories.py` in Legion — intent and safety review |

---

## 7. Runtime Entrypoints (DRAFT)

*Ground truth: verified read-only shell output at 2026-07-15 01:26 UTC.*
*STATUS: DRAFT — Legion engine is evolving. Banxe scan is INDICATIVE-ONLY (see §7.2 hygiene caveat).*

---

### 7.1 Legion / OpenManus — Runtime Entrypoints

#### 7.1.1 Top-level Python `__main__` / runnable scripts

| Script | Purpose |
|--------|---------|
| `demo_decision_framework.py` | Demo — decision framework |
| `example_decision_agent.py` | Example — decision agent |
| `merge_repositories.py` | Utility — repo merge/sync tooling |
| `openmanus_integration.py` | Primary integration entry point |
| `test_decision_framework.py` | Test runner — decision framework |
| `test_smart_decision_agent.py` | Test runner — smart decision agent |

#### 7.1.2 API servers (`openmanus_rl/api/`)

| File | Bind address | Port | S-18 §1.2 status |
|------|-------------|------|------------------|
| `health.py` | `127.0.0.1` | `8080` | OK — localhost only |
| `server.py` | `cfg["host"]` (comment: `127.0.0.1` default) | `cfg` | OK if default holds; see open question below |
| `streaming.py` | `127.0.0.1` | `8081` | OK — localhost only |

#### 7.1.3 Docker / Compose

| Artefact | Detail |
|----------|--------|
| `Dockerfile` | `EXPOSE 8000`; `CMD uvicorn openmanus_rl.api.server:app --host 0.0.0.0 --port 8000` |
| `docker-compose.yml` | Services: `openmanus` + `redis:7-alpine` |
| Ollama dependency | `http://localhost:11434`, model `qwen2.5:7b-instruct` (matches Legion baseline) |

#### 7.1.4 Vendored `verl/` sub-library servers

| File | Bind | Port | Notes |
|------|------|------|-------|
| `verl/.../local_dense_retriever/retrieval_server.py` | `0.0.0.0` | `8000` | uvicorn.run explicit |
| `verl/.../rollout/async_server.py` | `["::","0.0.0.0"]` | (config) | dual-stack wildcard |

---

### ⚠️ S-18 §1.2 OPEN QUESTION — NEEDS-OPERATOR-CONFIRMATION

> **Status: NEEDS-OPERATOR-CONFIRMATION — do NOT resolve without operator decision.**

S-18 §1.2 requires that the uncensored Legion engine remains isolated to localhost / `share=False`
and is never published on a routable network interface.

The following binds have been observed in the Legion codebase:

1. **`Dockerfile CMD`**: `uvicorn openmanus_rl.api.server:app --host 0.0.0.0 --port 8000`
2. **`verl/.../retrieval_server.py`**: `uvicorn.run(host="0.0.0.0", port=8000)`
3. **`verl/.../rollout/async_server.py`**: `host=["::","0.0.0.0"]` (IPv4 + IPv6 wildcard)

**Open question for operator:** Are any of these `0.0.0.0` / `[::]` binds ever published
to a routable interface via Docker port mapping (e.g., `-p 8000:8000` on a host with a
LAN/tailnet NIC)? If yes, S-18 remediation is required before the Legion engine is
considered network-isolated.

**Audit action:** record and escalate. **No code changes made.** A clean network topology
diagram (Legion container ↔ host ↔ external) is required to close this question.

---

### 7.2 banxe-emi-stack — Runtime Entrypoints (INDICATIVE ONLY)

> **⚠️ AUDIT HYGIENE CAVEAT — results below are INDICATIVE, NOT verified.**
>
> The entrypoint grep during this pass matched files under
> `.claude/worktrees/agent-*/` (nested agent worktrees), not the primary working tree.
> Git reported branch `agent/factory/ledgerenv/sandbox-fix @ b420464` — a different
> branch from the primary `fix/ledger-test-env @ 31f1cee`.
>
> **Required action for second pass:** exclude `.claude/worktrees/**` from all greps and
> audit the primary worktree on a clean branch (e.g., checked out at the backup tag
> `pre-reconcile/20260714 @ 2acf540`). Results below are informational only.

#### 7.2.1 API entrypoints (indicative)

| Artefact | Detail |
|----------|--------|
| `api/main.py` | FastAPI application root |
| APIRouter modules observed | `auth`, `sanctions`, `statements`, `lending`, `batch_payments` (and others) |

#### 7.2.2 Docker services (indicative)

| Dockerfile | `EXPOSE` | CMD / entrypoint |
|------------|----------|-----------------|
| `docker/Dockerfile.mcp` | `8100` | `python -m banxe_mcp` |
| `docker/Dockerfile.mock-aspsp` | `8888` | `uvicorn services.recon.mock_aspsp:app --host 0.0.0.0 --port 8888` |

Compose stack services observed (indicative): `postgres`, `clickhouse`, `redis`, `grafana`,
`n8n`, `superset`, `marble`, `mock-aspsp`, `banxe-mcp`.

**Note:** `mock-aspsp` binds `0.0.0.0:8888` — this is a test stub and not a production
service, but should be confirmed as network-isolated in the Docker Compose network config.
Record for second pass; no action taken here.

---

## Draft Status Notice

**This document is a DRAFT.**

A second, finer audit pass is planned once the Legion/OpenManus engine stabilises (it is actively evolving). The findings in this document reflect the state at `2026-07-14 01:21 UTC` (backup tag `pre-reconcile/20260714`). All facts herein are ground-truth from verified read-only shell output at that timestamp.

Do not treat this document as a final compliance artefact. It serves as the baseline snapshot for subsequent reconciliation phases.

---

*Generated by BANXE Factory Agent | Reconciliation Bootstrap v2 | Phase-1 Audit pass*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
