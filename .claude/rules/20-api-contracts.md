# API Contract Rules — BANXE AI BANK
# Rule ID: 20-api-contracts | Load order: 20
# Created: 2026-04-11 | IL-SK-01

## Backward Compatibility

- **No breaking changes without approved migration plan**: field removals, type changes,
  status value changes, and endpoint renames are breaking changes.
- **Additive-first**: new fields are optional with defaults; deprecated fields are kept for
  ≥ 2 release cycles before removal.
- **Versioning**: breaking changes require a new version path prefix (`/v2/`); old version
  is maintained until all consumers migrate.

## Semantic Validation

- **Validate semantics, not only shapes**: Pydantic schema validation is necessary but not
  sufficient. Business rules (amount > 0, IBAN checksum, currency is ISO 4217) must be
  validated explicitly.
- **Idempotency for create/submit operations**: payment submissions, account creation, KYC
  submissions must accept a client-supplied `idempotency_key` and return the same result
  on replay within the idempotency window.
- **Amount fields**: always `DecimalString` (string representation of decimal). Never `float`
  or bare `number`. Enforced by Pydantic validator and Semgrep rule `banxe-float-money`.

## Traceability

- **Request IDs on all inbound requests**: every API request must carry or generate a
  `X-Request-ID` header. Log it at entry and propagate downstream.
- **Correlation IDs for multi-step flows**: transfers, KYC, reconciliation generate a
  `correlation_id` that appears in all related log lines, events, and audit records.
- **Error responses include trace context**:
  ```json
  { "error": "InvalidAmount", "message": "...", "request_id": "...", "correlation_id": "..." }
  ```

## Documentation

- **Update API docs on any field or status change**: `docs/API.md` must reflect every change.
- **Changelog entry**: every API change gets an entry in the API changelog section.
- **OpenAPI schema**: FastAPI auto-generates; verify schema is correct after any model change
  by checking `/docs` or `/openapi.json`.
