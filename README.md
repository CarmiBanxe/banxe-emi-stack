# banxe-emi-stack

**BANXE AI Bank — EMI Backend (FCA Authorised)**

FastAPI-based AML/KYC compliance engine. Handles transaction monitoring, sanctions screening, PEP checks, SAR filing, and audit trail for the BANXE Electronic Money Institution.

---

## Quick Start

```bash
# 1. Clone and set up environment
git clone git@github.com:CarmiBanxe/banxe-emi-stack.git
cd banxe-emi-stack
cp .env.example .env  # fill in secrets

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Run tests
pytest --cov=src/compliance --cov-fail-under=80

# 4. Start services
make start
```

---

## Architecture

```
banxe-emi-stack/
├── api/                    ← FastAPI routers (v1)
│   ├── models/             ← Pydantic schemas
│   └── routers/            ← Endpoint handlers
├── src/compliance/         ← Core compliance engine
│   ├── verification/       ← AML/KYC verification agents
│   ├── adapters/           ← External service adapters (SumSub, Watchman)
│   ├── ports/              ← Port interfaces (DIP)
│   ├── utils/              ← Shared utilities
│   └── validators/         ← Compliance validators
├── tests/                  ← Pytest test suite (≥80% coverage)
├── docs/                   ← Architecture + audit reports
└── .ai/                    ← AI registries and reports
```

### Compliance Stack

| Layer | Component | Purpose |
|-------|-----------|---------|
| L1 | `compliance_validator.py` | Rule thresholds, forbidden patterns |
| L2 | `tx_monitor.py` | Behavioural AML scoring |
| L3 | `aml_orchestrator.py` | Decision engine |
| L4 | `sar_generator.py` | SAR auto-filing |
| Audit | `audit_trail.py` | ClickHouse immutable log |

---

## Development

```bash
make quality-gate   # typecheck + lint + format + tests
make lint           # ruff + bandit
make test           # pytest with coverage
make format         # ruff format
```

### Pre-commit

```bash
pre-commit install
pre-commit run --all-files
```

---

## Key Invariants (I-series)

- **I-05**: Financial amounts always `Decimal`, never `float`
- **I-08**: All AML decisions logged to audit trail before response
- **I-12**: SAR filing requires MLRO approval (no auto-bypass)
- **I-28**: CEO STOP check at orchestrator entry point

---

## CI/CD

GitHub Actions (`.github/workflows/`):
- `compliance-ci.yml` — lint + pytest + coverage gate
- `test-coverage.yml` — `--cov-fail-under=80`
- `banxe-verification-tests.yml` — compliance verification

---

## Docs

- `docs/VERIFY-2026-04-12.md` — Health audit report
- `docs/AUDIT-2026-04-12.md` — Full audit trail
- `QUALITY.md` — Quality standards
- `ROADMAP.md` — Development roadmap
