# Project Map — banxe-emi-stack
# Source: Full repo scan (FUNCTION 1 — Architecture Skill Orchestrator)
# Created: 2026-04-10 | Updated: 2026-04-13 (Sprint 14)
# Purpose: Living project structure and module map

## Stats (2026-04-13 — Sprint 14)

- Python files: ~120+ (services/ + api/ + src/) | LoC: ~18,000+
- Service modules: 24 | Test files: 60+ | Tests: 2,619 | Coverage: 87.00%
- API routers: 18 | Endpoints: 78 | Pydantic models: 30+
- Service adapters: 14 (Mock/Jube/Sardine/Modulr/SendGrid/Balleryne/Marble/Keycloak/Midaz/Stub…)
- Docker compose files: 3 | Docker services: 8 (3 always-on + 5 on-demand)
- Agents (swarm): 7 compliance agents + 1 coordinator
- Python: 3.12 | FastAPI: 0.111+ | Pydantic: 2.0+

## Top-level structure

```
banxe-emi-stack/
├── CLAUDE.md                 # Agent instructions (P0 scope, stack map, constraints)
├── CHANGELOG.md              # Keep-a-Changelog format (v0.1.0..v0.7.0)
├── QUALITY.md                # Quality tracking
├── ROADMAP.md                # Phase 1-4 feature roadmap
├── pyproject.toml            # Python project config (py312, ruff, pytest)
├── requirements.txt          # Runtime dependencies (~12 packages)
├── requirements-compliance.txt  # Compliance pipeline deps (chromadb, s-transformers)
│
├── .claude/                  # Claude Code configuration
│   ├── CLAUDE.md             # LucidShark + session continuity protocol
│   ├── settings.json         # PostToolUse hooks, MCP servers
│   ├── agents/               # 2 agents (recon, reporting)
│   ├── commands/             # 5 slash commands (Phase 3)
│   ├── hooks/                # 2 hook scripts (Phase 3)
│   ├── rules/                # 7 policy rules (Phase 3)
│   └── skills/lucidshark/    # LucidShark skill definition
│
├── .ai/                      # AI project intelligence (Phase 3+4)
│   ├── registries/           # 12 machine-readable maps (this file)
│   ├── reports/              # 7 human-readable reports (incl. phase6)
│   └── snapshots/            # Migration checkpoints
│
├── api/                      # FastAPI REST layer
│   ├── main.py               # FastAPI app entrypoint (14 routers)
│   ├── deps.py               # Dependency injection (auth resolver)
│   ├── models/               # 10 Pydantic model files (20+ models)
│   └── routers/              # 14 router files (42 endpoints)
│
├── services/                 # Business logic (22 modules, ~56 files)
│   ├── aml/                  # AML: tx monitor, SAR, velocity, thresholds [ACTIVE]
│   ├── fraud/                # Fraud pipeline, Jube + Sardine adapters [ACTIVE+STUB]
│   ├── kyc/                  # KYC workflow, Balleryne adapter [ACTIVE+STUB]
│   ├── hitl/                 # HITL queue, org roles, feedback loop [ACTIVE]
│   ├── payment/              # Modulr FPS/SEPA, webhook [ACTIVE+STUB]
│   ├── notifications/        # SendGrid email, mock [ACTIVE]
│   ├── customer/             # Customer CRUD, lifecycle [ACTIVE]
│   ├── ledger/               # Midaz CBS balance adapter [STUB]
│   ├── recon/                # CASS 7.15 reconciliation (10 files) [ACTIVE+STUB]
│   ├── reporting/            # FIN060 PDF, RegData returns [ACTIVE+STUB]
│   ├── case_management/      # Marble adapter, case factory [STUB]
│   ├── iam/                  # Keycloak IAM adapter [STUB]
│   ├── events/               # RabbitMQ event bus [ACTIVE]
│   ├── agreement/            # Agreement lifecycle [STUB]
│   ├── config/               # YAML/PostgreSQL config store [ACTIVE]
│   ├── consumer_duty/        # FCA PS22/9 assessment [ACTIVE]
│   ├── complaints/           # Consumer complaints + n8n [ACTIVE]
│   ├── auth/                 # 2FA authentication [ACTIVE]
│   ├── statements/           # Account statement service [ACTIVE]
│   ├── resolution/           # Resolution pack generation [ACTIVE]
│   ├── webhooks/             # Inbound webhook router [ACTIVE]
│   └── providers/            # Provider registry (factory pattern) [ACTIVE]
│
├── agents/compliance/        # AI compliance swarm (7 soul agents)
│   ├── swarm.yaml            # Swarm orchestration (Claude AI, tools, memory)
│   ├── soul/                 # 7 agent soul files
│   └── workflows/            # 2 compliance workflows
│
├── tests/                    # 47 test files | 1,102 tests | 86.89% coverage
├── scripts/                  # 17 operational/deploy scripts
├── dbt/                      # dbt-clickhouse models (6 files, FIN060 transforms)
├── docker/                   # 3 compose files + postgres init
├── config/                   # Runtime config (YAML, Keycloak, n8n, providers)
├── docs/                     # API.md, ONBOARDING.md, RUNBOOK.md
├── infra/ballerine/          # Ballerine KYC deployment
├── n8n/                      # n8n workflow definitions
├── prompts/                  # Workflow prompts (01-safety, 02-refactoring, 03-orchestrator)
└── .semgrep/                 # Custom security rules (10 rules)
```

---

## Service modules — status detail

| Module | Files | Domain | Status | Key class | Coverage |
|--------|-------|--------|--------|-----------|----------|
| `aml/` | 4 | AML/Compliance | ACTIVE | TxMonitorService, SARService, RedisVelocityTracker | 94%+ |
| `fraud/` | 5 | Fraud/PSR | ACTIVE+STUB | FraudAMLPipeline, JubeAdapter, SardineFraudAdapter | 85%+ |
| `kyc/` | 3 | KYC | ACTIVE+STUB | MockKYCWorkflow, BallerineAdapter | 94%+ |
| `hitl/` | 4 | Compliance Gate | ACTIVE | HITLService, OrgRoleChecker, FeedbackLoopAnalyser | 93%+ |
| `payment/` | 5 | Transactions | ACTIVE+STUB | PaymentService, ModulrPaymentAdapter | 67%+ |
| `notifications/` | 4 | Infra | ACTIVE | NotificationService, SendGridAdapter | 84%+ |
| `customer/` | 2 | Banking Core | ACTIVE | InMemoryCustomerService, ClickHouseCustomerService | 94%+ |
| `ledger/` | 2 | Banking Core | STUB | MidazLedgerAdapter, StubLedgerAdapter | 45% |
| `recon/` | 10 | Banking Core | ACTIVE+STUB | ReconciliationEngine, BreachDetector | 37–100% |
| `reporting/` | 3 | Reporting | ACTIVE+STUB | FIN060Generator, RegDataReturnService | 96% |
| `case_management/` | 4 | Compliance | STUB | MarbleAdapter, CaseFactory | unknown |
| `iam/` | 2 | Infra | STUB | KeycloakAdapter, MockIAMAdapter | 93% |
| `events/` | 1 | Infra | ACTIVE | RabbitMQEventBus | 94% |
| `agreement/` | 1 | Banking Core | STUB | — | unknown |
| `config/` | 2 | Infra | ACTIVE | YAMLConfigStore, PostgreSQLConfigStore | unknown |
| `consumer_duty/` | 2 | Compliance | ACTIVE | ConsumerDutyService | unknown |
| `complaints/` | 2 | Compliance | ACTIVE | ComplaintService (n8n webhook) | unknown |
| `auth/` | 1 | Infra | ACTIVE | TwoFactorService | unknown |
| `statements/` | 2 | Banking Core | ACTIVE | StatementService | 95% |
| `resolution/` | 1 | Compliance | ACTIVE | ResolutionPackService | 100% |
| `webhooks/` | 1 | Infra | ACTIVE | WebhookRouter | 95% |
| `providers/` | 1 | Infra | ACTIVE | ProviderRegistry (factory) | 87% |

## Adapters — swappable at runtime

| Adapter | Provider | Status | Env var to activate |
|---------|----------|--------|---------------------|
| MockFraudAdapter | Internal | ACTIVE (default) | FRAUD_ADAPTER=mock |
| JubeAdapter | Jube (gmktec:5001) | ACTIVE | FRAUD_ADAPTER=jube |
| SardineFraudAdapter | Sardine.ai | STUB | SARDINE_CLIENT_ID + SARDINE_SECRET_KEY |
| MockKYCWorkflow | Internal | ACTIVE (default) | — |
| BallerineAdapter | Balleryne (gmktec:3000) | STUB | — |
| MockCaseAdapter | Internal | ACTIVE (default) | — |
| MarbleAdapter | Checkmarble | STUB | MARBLE_API_KEY |
| MockIAMAdapter | Internal | ACTIVE (default) | — |
| KeycloakAdapter | Keycloak (gmktec:8180) | STUB | — |
| ModulrPaymentAdapter | Modulr (sandbox) | ACTIVE | MODULR_API_KEY |
| MockPaymentAdapter | Internal | ACTIVE (default) | — |
| SendGridAdapter | SendGrid | ACTIVE | SENDGRID_API_KEY |
| MockNotificationAdapter | Internal | ACTIVE (default) | — |
| MidazLedgerAdapter | Midaz (localhost:8095) | STUB | MIDAZ_TOKEN |

---

*Last updated: 2026-04-10 (FUNCTION 1 scan — post-Phase 6)*


## TRACK Update — 2026-04-13

### New modules (since 2026-04-10 scan)

| Module | Files | Domain | Status | Key class | Coverage |
|--------|-------|--------|--------|-----------|----------|
| `src/safeguarding/` | 5+ | Safeguarding/CASS15 | ACTIVE | PositionCalculator, BreachService, AuditLogger, SafeguardingService | 80%+ |
| `services/settlement/` | 3+ | Banking Core/Recon | ACTIVE | TriPartyReconciliationEngine | unknown |

### Updated stats (2026-04-13)

- Service modules: 22 → 24 (added safeguarding, settlement)
- Test files: 47 → 54+ (7+ new test files for safeguarding, recon, MCP)
- New infra: Alembic migrations, Makefile, doc-sync.py, post-task.sh
- New skills: `.claude/skills/` (LucidShark, supabase-postgres-best-practices)
- CI: mypy, bandit High, coverage pipeline hardened (commit 0638e07)
- Linting: Biome + Ruff expanded (IL-BIOME-01)
- GAPs closed: GAP-003, GAP-004, GAP-010, GAP-014, GAP-017, GAP-019, GAP-023, GAP-051

### Updated top-level additions

```
├── Makefile                 # Build/doc-sync automation (IL-092)
├── alembic/                 # Database migrations (Alembic)
├── src/safeguarding/        # CASS 15 safeguarding module (GAP-003, GAP-004)
├── docs/AGENTS.md           # Agent documentation
├── docs/AUDIT-2026-04-12.md # 9-repo audit report
└── biome.json               # Biome linter config (IL-BIOME-01)
```

## TRACK Update — Sprint 14 (2026-04-13)

### New files added in Sprint 14

| File | Purpose |
|------|---------|
| `docs/STUB-INVENTORY.md` | 41-entry stub catalogue (S14-01) |
| `tests/integration/__init__.py` | Integration test package init |
| `tests/integration/test_e2e_compliance_flow.py` | 19 E2E compliance integration tests (S14-02) |
| `tests/test_two_factor.py` | 30 TOTP service tests (coverage uplift S14-03) |
| `tests/test_reasoning_bank.py` | 26 ReasoningBank + API tests (S14-03) |
| `tests/test_markdown_parser.py` | 22 compliance_kb markdown parser tests (S14-03) |
| `tests/test_repo_watch.py` | 35 repo_watch service tests (S14-03) |
| `tests/test_config_modules.py` | 21 config module import coverage tests (S14-03) |

### Updated stats vs Sprint 13

| Metric | Sprint 13 | Sprint 14 |
|--------|-----------|-----------|
| Tests | 2,378 | 2,619 |
| Coverage | 82.18% | 87.00% |
| Test files | 54+ | 60+ |
| Integration tests | 0 | 19 |
| Docs files | 12 | 14 |

*Last updated: 2026-04-13 (Sprint 14)*
