# Project Map — banxe-emi-stack
# Source: Full repo structure analysis
# Created: 2026-04-10
# Migration Phase: 4
# Purpose: Living project structure and module map

## Stats (2026-04-10)

- Files: 249 | Directories: 65
- Service modules: 22 | Test files: 46 (995 tests)
- API endpoints: 42 | Docker compose files: 3
- Python deps: ~20 (requirements.txt) | Compliance deps: ~7 (requirements-compliance.txt)

## Top-level structure

```
banxe-emi-stack/
├── CLAUDE.md                 # Agent instructions (P0 scope, stack map, constraints)
├── CHANGELOG.md              # Keep-a-Changelog format (v0.1.0..v0.7.0)
├── QUALITY.md                # Quality tracking
├── ROADMAP.md                # Phase 1-4 feature roadmap
├── pyproject.toml            # Python project config
├── requirements.txt          # Runtime dependencies
├── requirements-compliance.txt  # Compliance pipeline dependencies
├── .env.example              # Environment variable template (34 vars)
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
│   ├── registries/           # Machine-readable persistent maps
│   ├── reports/              # Human-readable analysis
│   └── snapshots/            # Migration checkpoints
│
├── api/                      # FastAPI REST layer (IL-046)
│   ├── main.py               # FastAPI app entrypoint
│   ├── deps.py               # Dependency injection
│   ├── models/               # 10 Pydantic model files
│   └── routers/              # 13 router files (42 endpoints)
│
├── services/                 # Business logic (22 modules, 56 files)
│   ├── agreement/            # Banking core — agreement lifecycle
│   ├── aml/                  # AML thresholds, SAR, velocity, tx monitor
│   ├── auth/                 # 2FA authentication
│   ├── case_management/      # Marble adapter, case factory
│   ├── complaints/           # Consumer complaints + n8n webhook
│   ├── config/               # YAML config store (config-as-data)
│   ├── consumer_duty/        # PS22/9 consumer duty
│   ├── customer/             # Customer CRUD
│   ├── events/               # RabbitMQ event bus
│   ├── fraud/                # FraudAML pipeline, Jube + Sardine adapters
│   ├── hitl/                 # Human-in-the-loop feedback
│   ├── iam/                  # Keycloak IAM adapter
│   ├── kyc/                  # KYC workflow, mock adapter
│   ├── ledger/               # Midaz CBS client + adapter
│   ├── notifications/        # Email/SMS/Telegram notification
│   ├── payment/              # Modulr payments, FPS/SEPA/BACS
│   ├── providers/            # Provider registry (plugin architecture)
│   ├── recon/                # Safeguarding reconciliation (10 files)
│   ├── reporting/            # FIN060 PDF generation, RegData
│   ├── resolution/           # Resolution pack generation
│   ├── statements/           # Account statement service
│   └── webhooks/             # Webhook router
│
├── agents/compliance/        # AI compliance swarm (7 soul agents)
│   ├── swarm.yaml            # Swarm orchestration config
│   ├── soul/                 # 7 agent soul files
│   └── workflows/            # 2 compliance workflows
│
├── tests/                    # 46 test files (995 tests, coverage ≥80%)
├── scripts/                  # 17 operational/deploy scripts
├── dbt/                      # dbt-clickhouse models (6 files)
├── docker/                   # 3 compose files + postgres init
├── config/                   # Runtime config (YAML, Keycloak, n8n, providers)
├── docs/                     # API.md, ONBOARDING.md, RUNBOOK.md
├── infra/ballerine/          # Ballerine KYC deployment
├── n8n/                      # n8n workflow definitions
├── prompts/                  # Workflow prompts (Phase 4)
└── .semgrep/                 # Custom security rules (10 rules)
```

---
*Last updated: 2026-04-10 (Phase 4 migration)*
