<!-- lucidshark:start - managed by lucidshark init, do not edit manually -->
## LucidShark — REQUIRED: Scan After Every Code Change
Run `mcp__lucidshark__scan(fix=true)` after every Edit/Write. Before commits: `domains=["all"]`.
Do NOT report task as done until scan shows zero issues.
<!-- lucidshark:end -->

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
