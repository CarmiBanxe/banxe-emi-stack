# ADR-007: Decimal (Python) / DECIMAL(20,8) (SQL) for All Monetary Values

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-SK-01 (core invariant I-01)
**Author:** Moriel Carmi / Claude Code

---

## Context

IEEE 754 double-precision floating point produces rounding errors:

```python
>>> 0.1 + 0.2
0.30000000000000004
>>> 0.1 + 0.2 == 0.3
False
```

For an EMI handling GBP client funds, any float rounding error is a regulatory violation (FCA CASS 15 — client funds must be accounted for exactly). A £0.01 rounding error across 1 million transactions = £10,000 unaccounted client money.

Additionally, FCA PS25/12 (safeguarding) explicitly requires exact accounting of client fund balances.

---

## Decision

**Absolute rule: never use `float` for monetary values.**

| Layer | Type | Reason |
|-------|------|--------|
| Python code | `decimal.Decimal` | Exact decimal arithmetic |
| SQL columns | `DECIMAL(20,8)` (PostgreSQL/ClickHouse) | Exact storage, 8 decimal places |
| API payloads (in/out) | `str` (DecimalString) | No floating-point in transit |
| Redis | String representation (`"123.45"`) | No float serialisation |

---

## Enforcement

| Layer | Enforcement mechanism |
|-------|----------------------|
| Python | Semgrep rule `banxe-float-money` (ERROR severity) |
| Python | Ruff (type checking catches some cases) |
| API | Pydantic validator: `@validator("amount") def must_be_decimal(cls, v): assert isinstance(v, Decimal)` |
| Tests | All test assertions use `Decimal("123.45")`, never `123.45` |
| Code review | .claude/rules/10-backend-python.md — "No float for money" |

---

## Exceptions (Documented in Code)

ML model weights and probability scores (risk_score, confidence) MAY use float because:
1. They are not monetary values
2. Exact decimal arithmetic is not required for scoring

These are explicitly marked with `# nosemgrep: banxe-float-money` where they appear next to monetary code.

---

## Consequences

### Positive
- Exact arithmetic: `Decimal("0.10") + Decimal("0.20") == Decimal("0.30")` ✅
- FCA CASS 15 and PS25/12 monetary accuracy requirements satisfied
- Cross-service amounts always survive serialisation unchanged

### Negative / Risks
- Decimal operations are slower than float (acceptable for financial use)
- External APIs that return float amounts require conversion at boundary: `Decimal(str(float_value))`

### Mitigations
- Performance: financial services are not latency-critical; Decimal overhead is acceptable
- External float conversion: always convert via `str()` first: `Decimal(str(api_response["amount"]))` — never `Decimal(float_value)` directly (loses precision)

---

## References

- Invariant I-01 in `.claude/rules/financial-invariants.md`
- Semgrep rule: `.semgrep/banxe-rules.yml` → `banxe-float-money`
- Example correct usage: `services/recon/reconciliation_engine.py`
- Example incorrect (caught by Semgrep): `float(amount)` anywhere in services/
