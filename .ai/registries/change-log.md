# Change Log — AI Migration Tracking
# Source: CHANGELOG.md reference + migration tracking
# Created: 2026-04-10 | Updated: 2026-04-14 (Sprint 15)
# Migration Phase: 15
# Purpose: Ongoing change tracking for AI-assisted development

## Migration changelog

### 2026-04-14 — Sprint 15: PSD2 SCA Backend + Token Refresh + Stub Resolution + E2E Tests

**S15-01: POST /auth/sca — PSD2 SCA Backend**
- `services/auth/sca_service.py`: SCAService + InMemorySCAStore (OTP/biometric, dynamic linking, replay prevention, rate limiting)
- `api/models/sca.py`: SCAInitiateRequest/Response, SCAVerifyRequest/Response, SCAMethodsResponse
- `api/routers/auth.py`: POST /auth/sca/challenge (201), POST /auth/sca/verify (200/429), GET /auth/sca/methods/{id}
- `tests/test_api_sca.py`: 17 tests
- Commits: `feat(S15-01)`, `1ce9546`

**S15-05: POST /auth/token/refresh — PSD2 RTS Token Rotation**
- `api/models/auth.py`: refresh_token added to LoginResponse; TokenRefreshRequest/Response
- `api/routers/auth.py`: Login issues refresh_token (7d, jti); POST /v1/auth/token/refresh (rotation)
- `tests/test_api_token_refresh.py`: 8 tests (rotation, expiry, wrong type, bad signature)
- Commits: `feat(S15-05)`, `f2939c5`

**S15-06: 8/9 Stub Resolution**
- `services/compliance_kb/embeddings/embedding_service.py`: OpenAIEmbeddingService + env-var factory (EMBEDDING_ADAPTER=openai|sentence_transformers|inmemory)
- `services/experiment_copilot/agents/experiment_designer.py`: make_kb_port() factory (KB_ADAPTER=http → HTTPKBPort)
- `services/transaction_monitor/store/alert_store.py`: get_alert_store() factory (ALERT_STORE=inmemory|db)
- `docs/STUB-INVENTORY.md`: Sprint 15 Resolution Log (8 RESOLVED, 1 BLOCKED:EXTERNAL)
- Commits: `feat(S15-06)`, `80b467c`

### 2026-04-13 — Sprint 14: Stub Inventory + E2E Tests + Coverage 87% + SCA + Platform Registries

**S14-01: STUB-INVENTORY.md**
- Created `docs/STUB-INVENTORY.md` — 41 entries across 5 parts cataloguing all stubs/mocks/pragmas
- Key blockers documented: BT-001 (DocuSign/CEO), BT-002 (Midaz/DevOps), BT-003 (Keycloak/DevOps), BT-004 (Marble/CEO)
- Commit: `docs(S14-01): STUB-INVENTORY.md — 41 stub entries across banxe-emi-stack`

**S14-02: E2E Compliance Integration Tests**
- Created `tests/integration/__init__.py` + `tests/integration/test_e2e_compliance_flow.py`
- 19 integration tests: KYC approval/rejection, agreement KYC gate, case management, multi-product, MLRO EDD flow
- Tests run without external dependencies (InMemory adapters)
- Commit: `test(S14-02): E2E compliance flow integration tests — 19 tests`

**S14-03: Coverage uplift 82.18% → 87.00%**
- `tests/test_two_factor.py` — 30 tests for TOTPService (0% → ~95%)
- `tests/test_reasoning_bank.py` — 26 tests for ReasoningBankStore + API router (0% → ~90%)
- `tests/test_markdown_parser.py` — 22 tests for compliance_kb markdown parser (25% → ~95%)
- `tests/test_repo_watch.py` — 35 tests for all repo_watch services (0% → ~85%)
- `tests/test_config_modules.py` — 21 tests for small config modules
- Extended `tests/test_api_health.py` — health readiness error paths
- Extended `tests/test_experiment_copilot/test_experiment_store.py` — delete + rebuild tests
- pyotp installed for real TOTP generation in tests
- Total: 2378 → 2619 tests, 82.18% → 87.00% coverage
- Commit: `test(S14-03): coverage uplift 82→87% — two_factor, reasoning_bank, markdown_parser, repo_watch`

**S14-08: PSD2 SCA flow stubs (banxe-platform)**
- `packages/shared/src/tokens/` — 5 design token files (colors, typography, spacing, breakpoints, index)
- `packages/web/src/components/molecules/SCAChallenge.tsx` — PSD2 Art.97 SCA modal (web, WebAuthn stub)
- `packages/mobile/app/sca/index.tsx` — PSD2 Art.97 SCA screen (mobile, expo-local-authentication)
- Commit: `feat(S14-08): PSD2 SCA stubs — web modal + mobile screen + design tokens`

**S14-09 + S14-10: Registry updates**
- Created 8 new banxe-platform registries: tokens-map, sca-map, auth-map, types-map, store-map, api-map, integration-map, compliance-map
- Updated all 13 banxe-emi-stack registries (this entry)

### 2026-04-13 — Sprint 13: ArchiMate Pipeline + IAM Active + Case Mgmt + KYC Gate + Coverage

**S13-00: ArchiMate Import Pipeline**
- Renamed `import-archimate.py` → `import_archimate.py` (Python import compatibility)
- Updated Makefile `IMPORT_SCR` variable in `banxe-architecture/`
- Added `tests/test_import_archimate.py` — 32 tests (XML + CSV + registry roundtrip)

**S13-02: IAM STUB→ACTIVE — Keycloak JWKS offline JWT validation**
- Rewrote `KeycloakAdapter.validate_token()` in `services/iam/mock_iam_adapter.py`
- `_fetch_jwks()`: JWKS cache (300s TTL), `urllib.request.urlopen` → offline RS256 via PyJWT
- Added 51 tests in `tests/test_iam_adapter.py` — iam/ coverage 98%
- Commit: `feat(S13-02): IAM STUB→ACTIVE — Keycloak JWKS offline RS256 JWT validation`

**S13-03: Case Management — update/close/list**
- Extended `CaseManagementPort` Protocol: `update_case()`, `close_case()`, `list_cases()`
- Implemented in `MarbleAdapter` (HTTP PATCH/GET) and `MockCaseAdapter`
- Added 22 tests in `tests/test_case_management.py` (total 86 tests)
- Commit: `feat(S13-03): case management — update_case, close_case, list_cases`

**S13-04: Agreement lifecycle — KYC gate (FCA COBS 6)**
- `InMemoryAgreementService.__init__()` takes `kyc_checker: Callable[[str], KYCStatus | None]`
- `record_signature()` enforces KYC APPROVED before ACTIVE transition
- Added `TestKycGate` (17 tests) in `tests/test_agreement_service.py`
- Commit: `feat(S13-04): agreement KYC gate — FCA COBS 6 requires APPROVED KYC before signature`

**S13-05: Payment service coverage 67%→95%**
- Added 5 test classes: rail exceptions, ClickHouse failures, event bus, n8n webhook, factory
- Patches `httpx.post` and `N8N_WEBHOOK_URL` module var for webhook tests
- Commit: `feat(S13-05): payment_service coverage 67%→95% — rail, clickhouse, eventbus, n8n, factory`

**S13-06: Auth coverage 53%→100% + import_archimate test fix**
- Added `TestGetCustomerByEmailMemory` (3 tests), `TestGetCustomerByEmailDb` (2 async)
- Added `TestLoginHandlerDirect` (5 async tests): direct `login()` handler calls without HTTP
- Fixed `test_parse_element_properties`: property key `"prop-status"` → `"banxe-status"`
- `pyproject.toml`: `concurrency = ["thread"]` added to coverage.run
- Total: 2378 passed, 3 skipped, coverage 82.18%
- Commit: `feat(S13-06): auth.py coverage 53%→100%`

**S13-07: Registry sync (this entry)**
- Created `archimate-map.md` — 13th registry (ArchiMate pipeline metadata)
- Updated `domain-map.md`: IAM/agreement/case_mgmt status to ACTIVE+STUB
- Updated `change-log.md` (this entry)

### 2026-04-13 — Sprint 12: CASS 15 Safeguarding + Tri-Party Recon API
- Created `api/routers/safeguarding.py` — 6 CASS 15 endpoints (position, accounts, breaches, reconcile, resolution-pack, fca-return)
- Created `api/routers/recon.py` — 3 tri-party recon endpoints (status, report, history)
- Registered both routers in `api/main.py` (prefix `/v1`)
- Created `src/products/emi_products.py` — EMI product catalogue (GAP-014)
- Created `src/api/gateway.py` — API gateway with auth, rate-limiting, idempotency (GAP-023)
- Created tests: `test_api_safeguarding.py` (44 tests), `test_api_recon.py` (27 tests), `test_src_products.py` (35 tests), `test_src_api.py` (40 tests), `test_src_billing.py` (36 tests), `test_src_safeguarding_agent.py` (30 tests)
- Fixed CI: added `--cov=src` to pyproject.toml + quality-gate.yml; coverage now 80.92%
- Added mypy `[tool.mypy]` config to pyproject.toml; added mypy hook to .pre-commit-config.yaml
- Fixed Bandit B602: `shell=True` → list args in `services/design_pipeline/token_extractor.py`
- Merged `refactor/claude-ai-scaffold` → `main` (179 commits, 590 files)
- API total: 42 → 78 endpoints
- Test total: 2227 passed, 3 skipped
- Commit: `feat(safeguarding): CASS 15 API router + tri-party recon — Sprint 12`

### 2026-04-12 — Sprint 11: Statements + Auth + Compliance KB + Experiments + Transaction Monitor
- Added `api/routers/statements.py` — 2 statement download endpoints
- Added `api/routers/auth.py` — JWT login endpoint
- Added `api/routers/compliance_kb.py` — 8 RAG knowledge base endpoints
- Added `api/routers/experiments.py` — 8 A/B experimentation endpoints
- Added `api/routers/transaction_monitor.py` — 8 real-time monitoring endpoints
- Repo verification: 14/14 BANXE repos ✅ all 5 criteria

### 2026-04-10 — Phase 3: Scaffold Creation (CP-1)
- Created `.claude/rules/` — 7 modular policy files
- Created `.claude/commands/` — 5 slash-command workflows
- Created `.claude/hooks/` — 2 automation scripts (pre-commit, post-edit)
- Created `.ai/registries/`, `.ai/reports/`, `.ai/snapshots/` directories
- Created `prompts/` directory
- Updated `.gitignore` — added snapshots + local overrides patterns
- Commit: `scaffold(phase3): add Claude Code rules, commands, hooks`
- Branch: `refactor/claude-ai-scaffold`
- Tag: `pre-migration-2026-04-10` (base: `90fdd0e`)

### 2026-04-10 — Phase 10: Handoff + Prompt 3 Load (CP-4)
- Created `.ai/reports/phase6-validation-report.md` — full gate results
- Added `prompts/03-architecture-skill-orchestrator.md` — downloaded from Google Drive
- Tagged: `phase6-validated` (commit `a02b1d2`)
- Pushed: `refactor/claude-ai-scaffold` + tag → GitHub
- CHANGED: `.ai/reports/` (+2 files), `prompts/` (+1 file)
- ADDED: phase6 report, Prompt 3 (Architecture Skill Orchestrator)
- IMPACT ON WEB BUILD: none (additive docs only)
- IMPACT ON MOBILE BUILD: none
- IMPACT ON COMPLIANCE: none
- RECOMMENDED NEXT ACTION: Run FUNCTION 1 (SCAN) to verify project-map is current, then FUNCTION 3 (EXTRACT) for web/mobile readiness

### 2026-04-10 — Phase 5: System Intelligence Pass (CP-3)
- Rewrote `ui-map.md` (28 screens → 42 endpoints), `web-map.md`, `mobile-map.md`, `api-map.md`
- Fixed `shared-map.md` (env var count 30→32), `mobile-web-gap-analysis.md`
- Added `cross-registry-gaps.md` (5 gaps found and corrected)
- Commit: `411c960`

### 2026-04-10 — Phase 4: Content Migration (CP-2) [CURRENT]
- Populated `.ai/registries/` — 12 registry files from codebase analysis
- Populated `.ai/reports/` — 6 report files
- Copied prompt files to `prompts/`

## Source CHANGELOG summary (pre-migration)

| Version | Date | IL | Key changes |
|---------|------|-----|-------------|
| 0.7.0 | 2026-04-07 | IL-017 | CHANGELOG, RUNBOOK, ONBOARDING, API docs, OpenAPI spec |
| 0.6.0 | 2026-04-07 | IL-016 | Quality gate script, QualityGuard agent, Semgrep rules (10) |
| 0.5.0 | 2026-04-07 | IL-015 | BreachDetector, FIN060 PDF cron, 12+10 tests |
| 0.4.0 | 2026-04-07 | IL-014 | Quality sprint — centralised config, 80% coverage |
| 0.3.0 | 2026-04-07 | IL-014 | Payment rails — Modulr adapter, FPS/SEPA, 20 tests |
| 0.2.0 | 2026-04-06 | IL-013 | D-recon + J-audit — ReconciliationEngine, ClickHouse, daily-recon.sh |
| 0.1.0 | 2026-04-06 | IL-009..011 | P0 skeleton — services/, tests/, dbt/, FIN060 generator |

## Tracking format

New entries should follow:
```
### YYYY-MM-DD — [Phase/Feature]: [Description] (CP-N)
- Bullet list of changes
- Commit: `message`
- Branch: `branch-name`
```

---
*Last updated: 2026-04-10 (Phase 4 migration)*

### 2026-04-13 — TRACK: Sprint 12 completion + new modules (CP-5)

CHANGED:
- `services/recon/` — tri-party reconciliation engine added (GAP-010 D-recon DONE, commit `cabfb2f`)
- `services/` — `src/safeguarding/` module added CASS 15 implementation (GAP-003, GAP-004 DONE, commit `6668d7d`)
- `.claude/skills/` — BANXE dynamic skills directory added (commit `ed7c501`)
- `.claude/skills/supabase-postgres-best-practices` — new agent skill added (commit `bfcb9c4`)
- `CLAUDE.md` — Agent Skills section added (commit `f3aecd2`)
- `scripts/` — `post-task.sh` hook + `commit-log.jsonl` added IL-091 (commit `ee683db`)
- `scripts/doc-sync.py` — automatic documentation sync script added IL-091 (commit `b75626a`)
- `Makefile` — doc-sync targets added IL-092 (commit `16e409a`)
- `pyproject.toml` / linting — Biome + Ruff expanded ruleset integrated IL-BIOME-01 (commit `b8aea31`)
- `.claude/hooks/` — `post-task.sh` automation added
- `infra/` — systemd user-service for compliance-api :8093 added (commit `cc97e99`)
- `alembic/` — Alembic migration environment for safeguarding schema added (commit `21bc9a3`)
- `tests/` — 7+ new test files added (MCP tools, breach API, recon API, safeguarding API, AuditLogger, PositionCalculator, BreachService, ReconciliationService)
- `docs/AGENTS.md` + `README.md` added (commit `e060184`)
- `docs/AUDIT-2026-04-12.md` + `docs/VERIFY-2026-04-12.md` added
- `docs/ADR-001-biome-vs-eslint.md` added (commit `1307887`)

ADDED:
- `src/safeguarding/` — CASS 15 safeguarding module (new domain: Safeguarding)
- `.claude/skills/` — skills directory (LucidShark + supabase-postgres-best-practices)
- `scripts/post-task.sh`, `scripts/doc-sync.py`, `commit-log.jsonl`
- `alembic/` — database migration infrastructure
- `Makefile` — build/doc-sync automation
- `docs/AGENTS.md`, `docs/AUDIT-2026-04-12.md`, `docs/VERIFY-2026-04-12.md`

REMOVED: none

IMPACT ON WEB BUILD: medium — safeguarding module adds new API surface (CASS 15 position/breach endpoints) that needs web UI for compliance dashboard
IMPACT ON MOBILE BUILD: low — safeguarding data can be surfaced in mobile statements view; breach alerts relevant for mobile notifications
IMPACT ON COMPLIANCE: HIGH — CASS 15 safeguarding (GAP-003, GAP-004) now DONE; tri-party recon (GAP-010) DONE; Sprint 12 GAP-051,017,019,014,023 completed

DIRECTION CORRECTION: none — project is on track. Sprint 12 gaps closing rapidly. Quality pipeline (mypy, bandit, coverage) being hardened today (commit `0638e07`).

RECOMMENDED NEXT ACTION: Run FUNCTION 3 (EXTRACT) to update web-map.md and mobile-map.md with safeguarding module endpoints. Update project-map.md to reflect new `src/safeguarding/` module and raised test coverage.

- Scan date: 2026-04-13
- Commits reviewed: `0638e07`, `f44251b`, `cabfb2f`, `6668d7d`, `cc97e99`, `f3aecd2`, `bfcb9c4`, `ed7c501`, `9a61e1b`, `e060184`, `16e409a`, `ee683db`, `b75626a`, `b8aea31`, `1307887`, `21bc9a3`, `d2c1309`, `f5dd2ce` (Apr 11-13)
- GAPs closed since last scan: GAP-003, GAP-004, GAP-010, GAP-014, GAP-017, GAP-019, GAP-023, GAP-051

---
*Last updated: 2026-04-13 (FUNCTION 4 TRACK — Architecture Skill Orchestrator)*
