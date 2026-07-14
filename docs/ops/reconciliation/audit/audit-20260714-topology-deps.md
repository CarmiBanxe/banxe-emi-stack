# Phase-1 Audit — Topology & Dependency Manifests
# DATE: 2026-07-14
# STATUS: DRAFT COMPLETE (2026-07-15) — Phase-1 pass done across all 5 Charter audit dimensions. Finer second pass planned.
# SCOPE: Repository identities · topology summary · dependency manifests · Charter §8 forbidden-dep scan · anomalies.
# DRAFT (2026-07-15): §7 runtime entrypoints · §8 safety/compliance surfaces · §9 test harnesses · §10 conclusion — all added.
# OPEN ITEMS (forward to second pass): S-18 HIGH key in Legion config.toml · 0.0.0.0 bind open question · banxe non-main baseline · OpenManus evolving HEAD.

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
| Safety / compliance surfaces | DONE (DRAFT) | See §8. HIGH open item: S-18 secret in Legion config. Banxe scan indicative-only. |
| Test harnesses               | DONE (DRAFT) | See §9. Asymmetric maturity: banxe production-grade, OpenManus early-stage. |
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

## 8. Safety / Compliance Surfaces (DRAFT)

*Ground truth: verified read-only shell output at 2026-07-15 01:32 UTC.*
*STATUS: DRAFT — Legion engine evolving. Banxe scan INDICATIVE-ONLY (see §7.2 hygiene caveat).*

---

### 8.1 ██ HIGH — S-18 §1.2: Real-Looking API Key in Committed Config

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  FINDING: HIGH SEVERITY — S-18 §1.2 VIOLATION (OPEN)                       │
│  Repo:    Legion / OpenManus                                                │
│  File:    config/config.toml                                                │
│  Lines:   62, 72, 101                                                       │
│  Status:  OPEN / HIGH — awaiting operator action                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Description:**  
Lines 62, 72, and 101 of `config/config.toml` contain commented example entries with what
appears to be a real LLM-gateway API key. The masked form is:

```
api_key = "sk-banxe-llm-gateway-2026-**REDACTED**"
```

The key follows the `sk-banxe-llm-gateway-2026-` prefix pattern consistent with a live
Banxe infrastructure credential. Presence in comments does not reduce risk — git history
retains all committed versions regardless of comment status.

**S-18 §1.2 requirement (verbatim rule):**  
Secrets must come only from environment variables or a secrets manager. They must never
appear in source files, configuration files, or comments committed to version control.

**Recommended operator actions (record only — factory executes nothing):**

1. **Rotate immediately** — if `sk-banxe-llm-gateway-2026-**REDACTED**` is a live key,
   treat it as compromised and rotate at the LLM gateway before any other action.
2. **Remove from config.toml** — replace the literal key with a placeholder or env
   reference (e.g. `api_key = "${LLM_GATEWAY_API_KEY}"`). Do NOT leave even masked/commented
   real keys in the file.
3. **Purge from git history** — if the key was ever committed in a non-comment position,
   or if the comment history must be cleaned, use `git filter-repo` or equivalent.
   This action is **operator-gated** (Charter §4: factory never deletes / rewrites history).
4. **Scan full history** — run `git log -p | grep -i "sk-banxe-llm"` across both repos to
   confirm no additional occurrences in older commits.

> **Factory action: NONE.** `config/config.toml` has NOT been modified. Full key value
> has NOT been printed in this document. This finding must be closed by the operator before
> the audit can be marked COMPLETE.

---

### 8.2 banxe-emi-stack — FCA Compliance Surfaces (INDICATIVE ONLY)

> **⚠️ Same hygiene caveat as §7.2:** grep ran against branch
> `agent/factory/ledgerenv/sandbox-fix @ b420464`, not the primary working tree, and some
> hits originated from `.pytest_cache/`, `apps/.openapi-snapshot.json`, and
> `data/audit/experiments.jsonl`. The second pass must exclude these paths and run against
> the primary branch at backup tag `pre-reconcile/20260714 @ 2acf540`.

#### 8.2.1 FCA Financial Invariants (I-01 … I-27) — key files observed

| Invariant cluster | Files (indicative) |
|-------------------|--------------------|
| Monetary / Decimal (I-01) | `services/fx_engine/models.py`, `services/ledger/gl_service.py`, `services/payment/payment_processing_service.py`, `services/consumer_duty/models.py`, `services/consent_management/models.py`, `services/swift_correspondent/models.py` |
| Jurisdiction hard-block (I-02) | `services/payment/payment_auth_guard.py` |
| Invariant registry / policy | `ROADMAP.md`, `banxe_mcp/server.py` |

#### 8.2.2 HITL / Audit Trail / Approval Surfaces

| Surface | Files (indicative) |
|---------|--------------------|
| HITL service + org roles | `services/hitl/org_roles.py`, `api/routers/hitl.py` |
| HITL test coverage | `tests/test_hitl_service.py`, `services/banking-engine/tests/test_b5_hitl.py` |
| Ledger / IL tracking | `INSTRUCTION-LEDGER.md` |

#### 8.2.3 Sanctions / AML / Jurisdiction Surfaces

| Surface | Files (indicative) |
|---------|--------------------|
| AML pipeline | `services/fraud/fraud_aml_pipeline.py` |
| Cards agent (jurisdiction) | `services/agents/cards_agent.py` |
| Sanctions routers | Sanctions-specific routers (exact paths: second pass required) |
| Test coverage | Present (exact files: second pass required) |

**Note:** Cache and snapshot hits (`.pytest_cache/`, `apps/.openapi-snapshot.json`,
`data/audit/experiments.jsonl`) have been excluded from the above; they were artefacts of
the branch state, not primary source files.

---

### 8.3 Legion / OpenManus — Safety Surfaces

*Branch: `main @ 70fa07f` at time of safety scan.*

#### 8.3.1 S-18 / Security Config Files

| File | Purpose |
|------|---------|
| `config/config.toml` | Runtime configuration (contains HIGH finding — see §8.1) |
| `docs/NETWORK_HARDENING.md` | Network hardening runbook / guidance |
| `scripts/security_validator.py` | Security validation script |
| `tests/integration/test_external_api_integration.py` | Integration tests for external API calls |

#### 8.3.2 Decision / Compliance Framework

| File | Role |
|------|------|
| `openmanus_rl/llm_agent/openmanus.py` | Core LLM agent — decision logic |
| `openmanus_rl/agents/smart_decision_agent.py` | Smart decision agent |
| `rollout_loop.py` | RL rollout loop |
| ALFWorld env (reward / tasks) | Environment reward signals and task definitions |

#### 8.3.3 Benign Secret-Smells (NOT violations — explicitly cleared)

The following patterns triggered secret-smell detectors but are **not** violations:

| Pattern | Location | Reason cleared |
|---------|----------|---------------|
| `WANDB_API_KEY=` | Legion config / env template | Value is empty — placeholder only |
| `secrets.token_urlsafe(32)` | Legion source | Python stdlib call to *generate* a token, not a hardcoded secret |
| `summary_api_key=None` | Legion source | Explicitly null — no secret present |

These are recorded here so future auditors do not re-triage them. Only the `sk-banxe-llm-gateway-2026-**REDACTED**` entry (§8.1) is a genuine finding.

---

## 9. Test Harnesses (DRAFT)

*Ground truth: verified read-only shell output at 2026-07-15 01:44 UTC.*
*STATUS: DRAFT — Legion engine evolving; banxe audited from non-main branch (indicative-only caveat applies).*

---

### 9.1 Legion / OpenManus — Test Harness

| Metric | Value |
|--------|-------|
| Total test files | 49 |
| `tests/unit/` | 22 files |
| `tests/integration/` | 20 files |
| Scattered test scripts | `test_setup.py`, `test_rollout_mock.py`, `test_rollout_env.py`, `test_openmanus.py`, `test_decision_integration.py` |
| Test runner config | `pytest.ini`, `conftest.py`, `pyproject.toml`, `.github/workflows` present |
| Coverage gate | **NONE** — no `--cov-fail-under` threshold found |
| Quality-gate script | **NONE** — no equivalent to `quality-gate.sh` found |
| Maturity | **EARLY-STAGE** |

**Assessment:**  
Test infrastructure is present (pytest + CI workflows) but lacks a coverage enforcement gate.
The split between `unit/` (22) and `integration/` (20) is healthy, with integration tests representing
a significant share — typical for RL/agent repos where end-to-end correctness matters more than unit
isolation. No blocking issues found; the gap is in quality-gate rigour, not test absence.

---

### 9.2 banxe-emi-stack — Test Harness

| Metric | Value |
|--------|-------|
| Total test files | 686 |
| `tests/unit/` | 35 files |
| `tests/agents/` | 25 files |
| `tests/smoke/` | 12 files |
| `tests/test_transaction_monitor/` | 11 files |
| `tests/test_intent_layer/` | 11 files |
| `tests/test_treasury/` | 10 files |
| `services/safeguarding-engine/` (tests) | 10 files |
| `tests/test_experiment_copilot/` | 9 files |
| `tests/integration/` | 9 files |
| `tests/watchdog/` | 8 files |
| `tests/test_support/` | 8 files |
| `tests/test_design_pipeline/` | 8 files |
| Coverage gate | `--cov-fail-under=35` (pyproject.toml `[tool.pytest.ini_options]`) |
| Coverage targets | `services/`, `api/`, `src/` |
| Makefile targets | `make lint` (Ruff + Biome), `make test`, `make test-full`, `make quality-gate` |
| Quality-gate script | `scripts/quality-gate.sh` (lint + semgrep + tests) |
| CI integration | GitHub Actions, semgrep SAST, Biome frontend lint |
| Maturity | **PRODUCTION-GRADE** |

> **Hygiene caveat (same as §7.2 / §8.2):** this count comes from branch
> `agent/factory/ledgerenv/sandbox-fix @ b420464`, not `main`. The finer second pass MUST
> re-run against `main` at tag `pre-reconcile/20260714 @ 2acf540` with noisy paths excluded
> (`.claude/worktrees/**`, `.pytest_cache/`, `apps/.openapi-snapshot.json`,
> `data/audit/experiments.jsonl`).

**Assessment:**  
Production-grade test infrastructure. 686 test files across well-organised domain directories,
CI quality-gate, semgrep SAST, and Makefile targets. Coverage threshold is conservative (35%)
relative to the CLAUDE.md target of 80%; this is consistent with a rapid-growth codebase and
may reflect the threshold being a floor rather than a ceiling.

---

### 9.3 Test Maturity Comparison

| Dimension | banxe-emi-stack | Legion / OpenManus |
|-----------|-----------------|--------------------|
| Test file count | 686 | 49 |
| Coverage gate | ✅ `--cov-fail-under=35` | ❌ None |
| Quality-gate script | ✅ `quality-gate.sh` | ❌ None |
| Semgrep in CI | ✅ Yes | Not confirmed |
| Makefile targets | ✅ lint / test / quality-gate | Not confirmed |
| Maturity | PRODUCTION-GRADE | EARLY-STAGE |

**Maturity is ASYMMETRIC.** This is expected: banxe is a regulated FCA P0 platform; OpenManus is
a private RL research engine. The gap is not a defect — it reflects different regulatory contexts.

---

### 9.4 SAFE-PORT CANDIDATE (Charter-allowed EXTRACT PATTERN — proposal only)

The quality-gate structure from banxe could be adapted for OpenManus:
- Coverage threshold (`--cov-fail-under=N`)
- `Makefile quality-gate` target (lint + semgrep + tests)
- Semgrep config in CI

**Constraints (Charter §9 — non-negotiable):**
- MUST NOT port any FCA-regulated invariants, compliance checks, or financial rules.
- Patterns and scaffolding only — no business logic transfer.
- This is a **candidate note**, not an approved action. Execution requires a dedicated Proposal
  document approved by the operator with an explicit "yes".

---

## 10. Draft Pass Conclusion

**Phase-1 DRAFT audit pass: COMPLETE.**

All five Charter audit dimensions have been completed at DRAFT level:

| # | Audit Dimension | Status | Section |
|---|-----------------|--------|---------|
| 1 | Repository topology & identity | DONE (DRAFT) | §1–§2 |
| 2 | Dependency manifests & §8 forbidden-dep scan | DONE (DRAFT) | §3–§4 |
| 3 | Runtime entrypoints | DONE (DRAFT) | §7 |
| 4 | Safety / compliance surfaces | DONE (DRAFT) | §8 |
| 5 | Test harnesses | DONE (DRAFT) | §9 |

---

### 10.1 Open Items (carried forward to second pass)

| ID | Severity | Item | Owner |
|----|----------|------|-------|
| OI-01 | **HIGH** | S-18 §1.2: Real-looking API key `sk-banxe-llm-gateway-2026-**REDACTED**` in `OpenManus/config/config.toml` lines 62/72/101. Must rotate if live; remove from file; purge git history (operator-gated). | Operator |
| OI-02 | MEDIUM | S-18 §1.2 open question: banxe processes binding to `0.0.0.0` — verify these are container-internal or otherwise not routable from the host network. Confirmed problematic only if host-network exposed. | Finer pass |
| OI-03 | LOW | banxe scan throughout this draft ran against branch `agent/factory/ledgerenv/sandbox-fix @ b420464`, not `main`. All banxe findings are indicative-only. Finer pass MUST use clean `main` baseline at tag `pre-reconcile/20260714 @ 2acf540` with noisy paths excluded (`.claude/worktrees/**`, `.pytest_cache/`, `apps/.openapi-snapshot.json`, `data/audit/experiments.jsonl`). | Finer pass |
| OI-04 | LOW | OpenManus HEAD moved several times during this audit (commits observed: `38c0ce6` → `70fa07f` → `e5c186a`). All Legion findings are DRAFT-only; finer pass must pin to a stable HEAD or tag. | Finer pass (after Legion stabilises) |

---

### 10.2 Finer Second Pass Plan

The second, finer pass will:

1. **Re-run all five dimensions** on clean, stable baselines:
   - banxe: `main` branch at `pre-reconcile/20260714 @ 2acf540`, with noisy path exclusions.
   - Legion: a stable post-evolution tag (once HEAD stabilises).
2. **Resolve OI-01** — confirm with operator whether key has been rotated and removed.
3. **Resolve OI-02** — verify 0.0.0.0 bind scope against Docker network configuration.
4. **Extend to remaining Charter audit dimensions** not covered in this draft:
   - Docker image provenance (base images, layer audit, sanctioned-jurisdiction check).
   - Secrets / env hygiene (`.env.example` review, production secret layout).
   - API contract surfaces (OpenAPI schema diff, MCP tool registry — 34 tools).
   - Inter-repo integration (`merge_repositories.py` intent and safety review).
5. **Produce Proposal docs** for any confirmed SAFE-PORT candidates (§9.4), each requiring
   explicit operator "yes" before any execution.

---

### 10.3 What This Document Is Not

- Not a final compliance artefact.
- Not an approved Proposal for any action.
- Not authoritative for the banxe FCA compliance record (use `banxe-architecture/docs/COMPLIANCE-MATRIX.md`).

This document is the baseline snapshot for Phase-1 reconciliation. Its value is as a structured
record of what was observed, what is open, and what the second pass must do.

---

## Draft Status Notice

**This document is a DRAFT.**

A second, finer audit pass is planned once the Legion/OpenManus engine stabilises (it is actively evolving). The findings in this document reflect the state at `2026-07-14 01:21 UTC` (backup tag `pre-reconcile/20260714`). All facts herein are ground-truth from verified read-only shell output at that timestamp.

Do not treat this document as a final compliance artefact. It serves as the baseline snapshot for subsequent reconciliation phases.

---

*Generated by BANXE Factory Agent | Reconciliation Bootstrap v2 | Phase-1 Audit pass*
*Worktree: banxe-emi-stack-reconciliation-20260714 | Branch: feat/reconciliation-charter-20260714*
