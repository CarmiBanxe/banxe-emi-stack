# Testing Rules — BANXE AI BANK
# Rule ID: 30-testing | Load order: 30
# Created: 2026-04-11 | IL-SK-01

## Coverage Requirement

- **Tests required for all changed business logic**: any PR that touches `services/`, `api/`,
  `agents/`, or `banxe_mcp/` must include tests for the changed behaviour.
- **Task is not complete if tests are missing**: missing tests must be explicitly justified
  (e.g., "covered by integration test at X" or "deferred to IL-NN with tracking ticket").
  Silence is not justification.
- **Coverage threshold**: ≥ 80% on `services/` and `api/` (enforced by CI gate).

## Test Strategy

- **Targeted fast tests first**: unit tests with in-memory stubs run in < 1s per test.
  Integration tests (real DB, real MCP) are separate and opt-in.
- **InMemory stubs for external ports**: ledger, audit, FX, statement fetcher all have
  `InMemory` stub implementations used in unit tests (Protocol DI pattern).
- **No sleeping in tests**: use deterministic time injection or event-driven assertions.

## Critical Domain Negative Tests

These domains MUST have negative test cases (invalid input, boundary conditions, rejections):

| Domain | Required negatives |
|--------|--------------------|
| Payments | Negative amount, zero amount, blocked jurisdiction, duplicate idempotency key |
| Ledger | Overdraft beyond limit, currency mismatch, missing account |
| AML | Threshold exactly at £10k/£50k, sanctioned IBAN, PEP match |
| Auth | Expired token, wrong PIN, replay attack, missing 2FA |

## Test Naming

```python
def test_<component>_<scenario>_<expected_outcome>():
    # e.g. test_recon_engine_matched_transactions_returns_zero_discrepancy
```

## Test File Location

- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Contract tests: `tests/contract/`
- Existing tests follow `tests/test_*.py` pattern — maintain consistency.
