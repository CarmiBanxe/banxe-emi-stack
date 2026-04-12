# AGENTS.md — banxe-emi-stack

**Repository:** `~/banxe-emi-stack/`
**Version:** 1.0 | 2026-04-12
**Purpose:** BANXE EMI backend — AML/KYC compliance engine (FCA authorised)
**Stack:** Python 3.11+, FastAPI, pytest, ruff, bandit

---

## Core mission

AML/KYC compliance engine for BANXE Electronic Money Institution.
Deterministic rule-based transaction monitoring + ML risk scoring via Jube TM.

---

## Four-Partner Swarm

| # | Partner | Role |
|---|---------|------|
| 1 | **Claude Code** | Architect, reviewer, orchestrator |
| 2 | **Ruflo** | Multi-step flow orchestrator |
| 3 | **Aider CLI** | Sole code executor |
| 4 | **MiroFish** | Banking/FCA/fraud scenario simulator |

---

## Instruction hierarchy

1. Explicit user instruction
2. **I-series invariants** (`QUALITY.md`) — financial rules, AML invariants
3. `CLAUDE.md` — project context
4. `AGENTS.md` — this file
5. `~/.claude/CLAUDE.md` — global defaults

---

## Key invariants (I-series)

| Invariant | Rule |
|-----------|------|
| **I-05** | Financial amounts: `Decimal` only, never `float` |
| **I-08** | All AML decisions logged before response |
| **I-12** | SAR filing requires MLRO approval |
| **I-28** | CEO STOP check at orchestrator entry |

---

## Compliance layer architecture

```
L1: compliance_validator.py    ← thresholds, forbidden patterns
L2: tx_monitor.py              ← behavioural AML scoring
L3: aml_orchestrator.py        ← decision engine (APPROVE/HOLD/REJECT/SAR)
L4: sar_generator.py           ← SAR auto-filing
    audit_trail.py             ← ClickHouse immutable audit log
```

---

## Development commands

```bash
make quality-gate              # lint + typecheck + tests
pytest --cov=src/compliance --cov-fail-under=80
ruff check src/
bandit -r src/compliance/
pre-commit run --all-files
```

---

## Aider executor patterns

```bash
bash scripts/aider-banxe.sh --banxe    # compliance domain (default)
bash scripts/aider-banxe.sh --full     # complex architectural tasks
bash scripts/parallel-verify.sh --file src/compliance/tx_monitor.py
```

---

## MiroFish scenarios

Scenarios: banking/FCA/fraud  
Location: `banxe-mirofish/scenarios/`  
Use for: pre-deploy gate on compliance rule changes

---

## Repository structure

```
banxe-emi-stack/
├── api/                ← FastAPI routers + schemas
├── src/compliance/     ← Core compliance engine
│   ├── verification/   ← AML/KYC agents
│   ├── adapters/       ← External service adapters
│   └── validators/     ← Compliance validators
├── tests/              ← pytest (≥80% coverage)
├── docs/               ← Architecture + audit reports
└── .ai/                ← AI registries and reports
```

---

## Definition of done

- [ ] Tests pass (`pytest --cov-fail-under=80`)
- [ ] `pre-commit run --all-files` green
- [ ] No new I-series violations
- [ ] Audit trail entries verified
- [ ] MLRO approval for SAR-related changes
