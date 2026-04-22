# INSTRUCTION LEDGER — banxe-emi-stack

## IL-LINT-01 — Ruff + Biome + Bandit + MyPy Canon Infrastructure
- Status: DONE
- Proof commit: 1c75213 (baseline)
- Scope: infrastructure only
- Artifacts: pyproject.toml [tool.ruff], frontend/biome.json schema 2.3.0, .pre-commit-config.yaml, .github/workflows/lint-*.yml + quality-gate.yml

## IL-LINT-02 — Bandit Nosec Rationale + gitignore Hardening
- Status: DONE
- Proof commit: 1c75213
- Scope:
  - nosec B310 provider_registry (scheme-validated health_url)
  - nosec B108 regdata_return stub (tracked by IL-FIN060-REAL-01)
  - nosec B104 safeguarding-engine (container-internal bind)
  - .gitignore: node_modules, caches

## IL-LINT-03 — Quality Baseline Remediation (OPEN)
- Status: TODO
- Scope deferred: B017 FrozenInstanceError migration, SIM300 Yoda conditions, defusedxml B314 migration (blocked: behaviour diff in test_camt053_parser)
