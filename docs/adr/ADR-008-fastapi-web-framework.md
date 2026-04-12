# ADR-008: FastAPI as Web Framework for All REST Services

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-046
**Author:** Moriel Carmi / Claude Code

---

## Context

The EMI stack needs async REST APIs for compliance, payment, KYC, AML, reporting, and monitoring services. Options evaluated:

- **Flask**: synchronous by default, no built-in OpenAPI, requires extensions for everything
- **Django REST Framework**: heavy, ORM-coupled, overkill for microservice APIs
- **aiohttp**: low-level, no automatic schema validation, no OpenAPI generation
- **FastAPI**: async-native, Pydantic v2, auto-OpenAPI, dependency injection

---

## Decision

**FastAPI** (async, Pydantic v2 validation, auto-OpenAPI at `/docs`, Python 3.12+) for all REST services.

---

## Rationale

| Criterion | FastAPI | Flask | Django REST | aiohttp |
|-----------|---------|-------|-------------|---------|
| Async-native | Yes | No (requires eventlet/gevent) | Partial | Yes |
| Pydantic v2 | Built-in | Manual | Manual | Manual |
| Auto-OpenAPI | Yes (/docs, /openapi.json) | No | drf-spectacular | No |
| Dependency injection | Yes (Depends()) | No | No | No |
| Type validation at boundary | Yes (Pydantic models) | Manual | Serializers | Manual |
| Performance | High (starlette) | Medium | Medium | High |
| Financial validation (Decimal, IBAN) | Via Pydantic validators | Manual | Manual | Manual |

---

## Current Routers (18 total)

| Router | Prefix | IL |
|--------|--------|----|
| `auth` | `/v1/auth` | IL-028 |
| `customers` | `/v1/customers` | IL-032 |
| `kyc` | `/v1/kyc` | IL-055 |
| `payments` | `/v1/payments` | IL-046 |
| `ledger` | `/v1/ledger` | IL-046 |
| `statements` | `/v1/statements` | IL-054 |
| `compliance_kb` | `/v1/kb` | IL-069 |
| `experiments` | `/v1/experiments` | IL-070 |
| `transaction_monitor` | `/monitor` | IL-071 |
| `fraud` | `/v1/fraud` | IL-049 |
| `health` | `/health` | IL-046 |
| `hitl` | `/v1/hitl` | IL-056 |
| `consumer_duty` | `/v1/consumer-duty` | IL-050 |
| `notifications` | `/v1/notifications` | IL-047 |
| `mlro_notifications` | `/v1/mlro` | IL-068 |
| `reporting` | `/v1/reporting` | IL-052 |
| `sanctions_rescreen` | `/v1/sanctions` | IL-068 |
| `watchman_webhook` | `/webhooks/watchman` | IL-068 |

---

## Conventions

- **Route handlers are thin**: all business logic in `services/` layer, not in route functions.
- **Request validation**: Pydantic models in `api/models/` — amounts always `DecimalString`.
- **Response models**: explicit `response_model=` on all routes.
- **X-Request-ID**: all requests carry or generate a request ID (logged at entry).
- **Error format**: `{"error": "ErrorType", "message": "...", "request_id": "..."}`.

---

## Consequences

### Positive
- Auto-generated OpenAPI at `/docs` — always up-to-date with code
- Pydantic v2 validators enforce financial invariants at the API boundary (I-01, I-05)
- `Depends()` pattern wires up Protocol DI ports cleanly

### Negative / Risks
- FastAPI's `Depends()` pattern is not composable outside HTTP context (use Protocol DI in services)
- Growing number of routers (18) requires careful prefix management

### Mitigations
- Router prefixes documented in this ADR and in `docs/API.md`
- Pydantic validators for Decimal amounts in `api/models/` prevent float leakage

---

## References

- `api/routers/` — all 18 routers
- `api/main.py` — FastAPI app factory
- `docs/API.md` — endpoint documentation
- ADR-005: Protocol DI (used in Depends() factory functions)
