<!-- quality-scanner status — corrected 2026-07-27 -->
## Quality Scanner — ACTUAL state
Primary gate (REAL, runs on every commit): semgrep with the repo's own fintech rules
(.semgrep/banxe-rules.yml) via .githooks/pre-commit, after .githooks/role-guard.sh.
Also available: ruff, mypy, bandit, pytest, coverage (see pyproject.toml, scripts/quality-gate.sh).
LucidShark: OPTIONAL / NOT INSTALLED here (pip pkg is 0.0.0.dev0 stub; no working binary;
no install.sh in repo). If a real LucidShark binary/MCP is provisioned, its hooks/skill
(.claude/skills/lucidshark, .claude/hooks/post-edit-scan.sh) will pick it up; until then it is
NOT required and NOT a blocker. Do NOT claim a task is blocked on LucidShark.
<!-- end quality-scanner status -->

---

## BANXE EMI Stack — Core Rules

### Financial Invariants (ALWAYS)
- **I-01**: `Decimal` for ALL £GBP amounts. NEVER `float`.
- **I-02**: Hard-block jurisdictions: RU/BY/IR/KP/CU/MM/AF/VE/SY
- **I-04**: EDD threshold £10k individual / £50k corporate
- **I-08**: ClickHouse TTL 5 years minimum (FCA retention)
- **I-24**: Append-only audit trails. NEVER delete.
- **I-27**: HITL — AI PROPOSES, human DECIDES. Never autonomous.

### Architecture Pattern
- Hexagonal: Port (Protocol) → Service → Adapter (Mock/Real)
- Tests: InMemory stubs, no external deps. ≥15 tests per component.
- Coverage ≥80%. Ruff clean. Semgrep clean.

### Stack
- Python 3.12, FastAPI, Pydantic v2, PostgreSQL, ClickHouse, Redis
- Frontend: React 19, TypeScript, Tailwind, Expo (mobile)
- Auth: Keycloak 26.2 on :8180 (IAM_ADAPTER=keycloak)
- Fraud: Jube :5001, Marble :5002, Moov Watchman
- KYC: Ballerine (self-hosted :3000)

### Session Protocol
On start: show last IL, test count, pending tasks, P0 deadline.
After task: check `INSTRUCTION-LEDGER.md` for pending items.

### Quality Gate (before declaring done)
1. LucidShark scan clean
2. `ruff check` + `ruff format` clean
3. All tests pass
4. Semgrep 0 findings
5. Update INSTRUCTION-LEDGER.md

<!-- Infrastructure checklist details: @.claude/rules/ -->
<!-- Skill details: @.claude/skills/README.md -->
<!-- Full compliance matrix: @../../banxe-architecture/docs/COMPLIANCE-MATRIX.md -->
