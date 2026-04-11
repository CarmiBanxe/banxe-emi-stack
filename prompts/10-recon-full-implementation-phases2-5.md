# 10 — Recon Full Implementation (Phases 2-5) — Claude Code Prompt

## Created: 2026-04-11 | IL-015 | Migration Phase: 4

## Context

You are working on **banxe-emi-stack** (branch `refactor/claude-ai-scaffold`).
Task: fully implement Reconciliation & Breach Detection feature (Phases 2-5).

## WHAT ALREADY EXISTS (Phase 1 — done)

Code:
- `services/recon/reconciliation_engine.py` (199 lines) — ReconciliationEngine, ReconResult, FCA CASS 7.15, Protocol DI
- `services/recon/breach_detector.py` (199 lines) — BreachDetector, BreachRecord, CASS 15.12, n8n webhook
- `services/recon/clickhouse_client.py` (324 lines) — ClickHouseReconClient + InMemoryReconClient
- `services/recon/statement_fetcher.py` (121 lines) — StatementFetcher, CSV Phase 1
- `services/recon/bankstatement_parser.py` — CSV/MT940 parser
- `services/recon/cron_daily_recon.py` — cron entry point
- `services/recon/midaz_reconciliation.py` — CLI (`python3 -m`)
- `services/recon/mock_aspsp.py` — mock bank API
- `services/recon/statement_poller.py` — polling loop
- `n8n/workflows/safeguarding-shortfall-alert.json` (129 lines) — base webhook workflow
- `agents/compliance/` — orchestrator.py, agent_runner.py, soul/, workflows/
- `tests/test_reconcilia*.py`, `tests/test_statemen*.py` — existing tests
- `docs/API.md` — API reference
- `docs/ARCHITECTURE-RECON.md` — Block D architecture
- `prompts/09-recon-breach-detection-prompt.md` — prompt

Infra:
- `docker/docker-comp*.yml` — docker compose files
- `.semgrep/banxe-rules.yml` — custom semgrep rules
- `.claude/rules/` — 8 rule files including `infrastructure-utilization.md`
- `.claude/hooks/` — post-edit-scan, pre-commit-q
- `.claude/commands/recon-status.md` — /recon-status command
- `banxe_mcp/server.py` — MCP server (FastMCP)
- `.ai/registries/`, `.ai/reports/`
- `agents/compliance/soul/` — 7 soul files (aml, cdd, fraud, jube, mlro, sanctions, tm)
- `agents/compliance/workflows/` — monthly_com, quarterly_boar
- `dbt/` — dbt project
- ClickHouse on GMKtec server (via Tailscale)

## CANONICAL RULES (violation = reject PR)

1. Decimal-only — NEVER float for money. All amounts Decimal, passed as str to ClickHouse
2. Protocol DI — all dependencies via typing.Protocol
3. InMemory stubs — every Protocol has in-memory implementation for tests
4. CTX-06 AMBER — ReconciliationEngine -> LedgerPort only, never Midaz HTTP direct
5. After every change: `pytest tests/ -k recon -x`
6. Atomic commits — one commit per logical unit
7. INFRASTRUCTURE CHECKLIST — must use ALL project resources (see .claude/rules/infrastructure-utilization.md)

## PHASE 2: Production ASPSP Integration

2.1. Enhance `services/recon/statement_fetcher.py`:
   - Add `fetch_phase2()` — HTTP client for real ASPSP API (Open Banking UK)
   - OAuth2 authentication (client_credentials flow)
   - Env vars: ASPSP_BASE_URL, ASPSP_CLIENT_ID, ASPSP_CLIENT_SECRET, ASPSP_CERT_PATH
   - Retry logic: 3 attempts with exponential backoff
   - Fallback to CSV drop if API unavailable

2.2. Enhance `services/recon/bankstatement_parser.py`:
   - MT940 (SWIFT) format parsing
   - CAMT.053 (ISO 20022 XML) — SEPA standard
   - Validation: sum of transactions = closing - opening balance
   - Account ID mapping: IBAN -> Midaz UUID

2.3. Enhance `services/recon/statement_poller.py`:
   - Async polling loop (asyncio)
   - Schedule: daily 06:00 UTC, retry 09:00, 12:00, then PENDING
   - Tests with InMemory ASPSP mock

2.4. Tests:
   - `tests/test_statement_fetcher_phase2.py`
   - `tests/test_bankstatement_parser_mt940.py`
   - `tests/test_statement_poller_async.py`

## PHASE 3: ClickHouse Production Schema + Grafana

3.1. Create `infra/clickhouse/migrations/`:
   - `001_create_safeguarding_events.sql`
   - `002_create_safeguarding_breaches.sql`
   - `003_create_recon_summary_mv.sql` (MaterializedView)
   - README.md with migration instructions

3.2. Create `infra/grafana/dashboards/safeguarding-recon.json`:
   - Panel 1: Daily recon status (stacked bar)
   - Panel 2: Discrepancy trend (line chart)
   - Panel 3: Active breaches (table)
   - Panel 4: Days since last MATCHED (stat, alert if >1)
   - Panel 5: Breach history timeline

3.3. Update docker-compose with ClickHouse + Grafana services

3.4. Enhance `services/recon/clickhouse_client.py`:
   - `get_discrepancy_streak()` — production SQL
   - `get_recon_summary(date_from, date_to)` — dashboard API
   - Connection pooling with retry

## PHASE 4: FCA RegData Auto-Submission via n8n

4.1. Enhance `n8n/workflows/safeguarding-shortfall-alert.json`:
   - Slack #compliance-alerts + @compliance-officer
   - Email CEO + CTIO
   - FCA RegData API (mock URL for sandbox)
   - Audit log to ClickHouse banxe.fca_notifications
   - Telegram bot notification

4.2. Create `n8n/workflows/daily-recon-report.json`:
   - Cron 18:00 UTC daily
   - Query ClickHouse summary
   - Slack #daily-recon

4.3. Create `services/recon/fca_regdata_client.py`:
   - FCARegDataClient with Protocol
   - Mock implementation for sandbox
   - Env vars: FCA_REGDATA_URL, FCA_REGDATA_API_KEY, FCA_FIRM_REFERENCE

4.4. Migration: `infra/clickhouse/migrations/004_create_fca_notifications.sql`

## PHASE 5: AI Agent Integration

5.1. Enhance `agents/compliance/orchestrator.py`:
   - Register ReconAnalysisSkill and BreachPredictionSkill

5.2. Create `agents/compliance/skills/recon_analysis.py`:
   - Analyze discrepancy patterns: TIMING_DIFFERENCE | MISSING_TRANSACTION | SYSTEMATIC_ERROR | FRAUD_RISK
   - Uses Ollama local LLM for pattern analysis
   - Output: AnalysisReport dataclass

5.3. Create `agents/compliance/skills/breach_prediction.py`:
   - Statistical prediction (moving average + trend)
   - Pure Python with Decimal math (no ML dependency)
   - Output: PredictionResult dataclass

5.4. Create soul files:
   - `agents/compliance/soul/recon_analysis_agent.soul.md`
   - `agents/compliance/soul/breach_prediction_agent.soul.md`

5.5. Create workflow:
   - `agents/compliance/workflows/daily_recon_workflow.py`

5.6. MCP Server tools in `banxe_mcp/server.py`:
   - `get_recon_status(date)` -> last ReconResult
   - `run_reconciliation(date, dry_run)` -> execute reconcile
   - `get_breach_history(account_id, days)` -> breach history

5.7. AI Registry: register recon agents in `.ai/registries/`

5.8. Semgrep: add `no-float-in-recon` rule to `.semgrep/banxe-rules.yml`

5.9. dbt: create `dbt/models/recon/` with safeguarding_events analytics models

## EXECUTION ORDER

1. Phase 2 -> commit -> pytest
2. Phase 3 -> commit -> pytest
3. Phase 4 -> commit -> pytest
4. Phase 5 -> commit -> pytest
5. Update docs/API.md
6. Update docs/ARCHITECTURE-RECON.md
7. Update prompts/09 roadmap all checkmarks
8. Final docs commit

Commit messages:
- `feat(recon): Phase 2 -- ASPSP integration + MT940/CAMT.053 parser [IL-015]`
- `feat(recon): Phase 3 -- ClickHouse production schema + Grafana dashboard [IL-015]`
- `feat(recon): Phase 4 -- FCA RegData auto-submission + n8n workflows [IL-015]`
- `feat(recon): Phase 5 -- AI agent recon analysis + breach prediction [IL-015]`
- `docs: update API.md + ARCHITECTURE-RECON.md for Phases 2-5 [IL-015]`

## INFRASTRUCTURE CHECKLIST (must be filled before done)

```
INFRASTRUCTURE CHECKLIST -- Recon/Breach Phases 2-5
[ ] LucidShark scan clean
[ ] Semgrep rules added (no-float-in-recon)
[ ] Claude Rules coverage
[ ] Claude Commands (/recon-status)
[ ] AI Agent Soul files (recon_analysis, breach_prediction)
[ ] Agent Workflow (daily_recon_workflow)
[ ] Orchestrator registration
[ ] MCP Server tools (get_recon_status, run_reconciliation, get_breach_history)
[ ] AI Registry
[ ] n8n Workflows (shortfall-alert enhanced, daily-recon-report)
[ ] Docker services (ClickHouse, Grafana)
[ ] dbt models (recon/)
[ ] Grafana dashboard (safeguarding-recon.json)
[ ] Tests passing
```

## AFTER COMPLETION

Print filled checklist table:
| Phase | Files | Tests | Status |
Run: `pytest tests/ -k recon -v --tb=short`
