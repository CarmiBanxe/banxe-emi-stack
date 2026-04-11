# Backend Python Rules — BANXE AI BANK
# Rule ID: 10-backend-python | Load order: 10
# Created: 2026-04-11 | IL-SK-01

## Data Flow

- **Explicit data flow**: every function must make clear what data enters and what leaves.
  Avoid implicit side effects on shared state.
- **Domain logic separate from framework**: business rules live in `services/`, not in FastAPI
  route handlers or Pydantic models.
- **No hidden global state**: module-level mutable state is forbidden. Use dependency injection
  or constructor parameters to pass configuration.
- **Typed boundaries**: all public functions and class methods must have full type annotations
  (parameters + return type). Use `typing.Protocol` for external dependencies.

## Financial Safety

- **Fail loudly on invalid financial inputs**: raise a specific, named exception
  (e.g., `InvalidAmountError`, `NegativeBalanceError`) rather than silently coercing.
- **No float for money**: use `Decimal` everywhere. Semgrep rule `banxe-float-money` enforces this.
- **Decimal strings in API layer**: amounts cross service boundaries as strings, not Decimal objects.

## Change Discipline

- **No mixed refactor + behaviour change**: a PR either refactors (no behaviour change, tests
  stay green) or adds/changes behaviour (new tests required). Never both at once.
- **Structured errors**: use custom exception classes with `code`, `message`, and optional
  `context` fields. Never raise bare `Exception`.
- **Never log secrets**: no passwords, tokens, card numbers, IBAN, or NI numbers in log lines.
  Use masked representations (`****`, `IBAN[last4]`) for debugging context.

## Code Style

- Ruff for linting and formatting (see `quality-gates.md`).
- Python 3.12+. Use `match` over long `if/elif` chains for dispatch.
- Async-first for I/O: all DB, HTTP, and MCP calls must be `async def`.
- Protocol DI pattern for all external ports (ledger, audit, FX, statement fetcher).
