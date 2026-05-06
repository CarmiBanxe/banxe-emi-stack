# SESSION-2026-05-06 — SCA + 2FA coverage uplift (Sprint 4 Track A)

**Branch:** `sprint4/sca-2fa-coverage-uplift`
**Base:** `main` @ `ec6142e`
**Canon:** ADR-015 + ADR-025 + AUTH_MATRIX.md + AUTH_IMPORT_ORDER.md + IL-CANON-OPERATOR-2026-05
**Source canon:** `NEXT_SESSION_START.md` / `AUTH_REFACTOR_TASKS.md`

---

## Goal

Поднять покрытие 4 модулей SCA + 2FA-стека до целевых уровней без правок
production-кода в `services/auth/*` и без касания `api/routers/auth.py`.

| Module | Target | Reason |
|---|---|---|
| `services.auth.sca_service` | ≥ 80 % | core domain |
| `services.auth.sca_application_service` | ≥ 90 % | application boundary |
| `services.auth.two_factor` | ≥ 80 % | TOTP service |
| `services.auth.two_factor_port` | = 100 % | Protocol port |

---

## Baseline (before, existing tests only)

Прогон:
```
pytest -o addopts="" \
  --cov=services.auth.sca_service \
  --cov=services.auth.sca_application_service \
  --cov=services.auth.two_factor \
  --cov=services.auth.two_factor_port \
  --cov-report=term-missing \
  tests/auth tests/test_api_sca.py tests/test_api_sca_resend.py \
  tests/test_api_sca_two_factor_integration.py \
  tests/test_sca_service_edge.py tests/test_sca_service_port.py \
  tests/test_sca_service_two_factor_port.py \
  tests/test_two_factor.py tests/test_two_factor_port.py
```

| Module | Stmts | Miss | Cover | Missing lines |
|---|---:|---:|---:|---|
| `services/auth/sca_application_service.py` | 48 | 4 | **92 %** | 76, 127–129 |
| `services/auth/sca_service.py` | 130 | 3 | **98 %** | 90, 355–357 |
| `services/auth/two_factor.py` | 112 | 4 | **96 %** | 100–101, 209–210 |
| `services/auth/two_factor_port.py` | 4 | 0 | **100 %** | — |
| **TOTAL** | **294** | **11** | **96 %** | — |

**Tests passed (baseline):** 83.

---

## Missing-line classification

| Module | Lines | Branch class | Why uncovered |
|---|---|---|---|
| `sca_application_service.py` | 76 | error mapping | `ValueError` → `invalid_method` path not invoked at app boundary (existing tests use FastAPI layer) |
| `sca_application_service.py` | 127–129 | DI lazy singleton | `get_sca_application_service()` global singleton — bypassed by tests that build `ScaApplicationService(...)` directly |
| `sca_service.py` | 90 | boundary cleanup | `InMemorySCAStore.delete()` — no consumer in current code path |
| `sca_service.py` | 355–357 | port-fallback | `_verify_otp` `ImportError` fallback for `pyotp` (no port + no pyotp) |
| `two_factor.py` | 100–101 | port-fallback | `setup_totp` `ImportError` if `pyotp` missing |
| `two_factor.py` | 209–210 | port-fallback | `_do_verify_totp` `ImportError` if `pyotp` missing |

Все classified-ветви соответствуют допустимым категориям задачи: **happy / error / boundary / port-fallback**.

---

## Tests added (no `services/auth/*` modifications)

| File | Purpose | New tests |
|---|---|---:|
| `tests/_fakes/__init__.py` | Test-fakes package marker | — |
| `tests/_fakes/two_factor_fake.py` | `FakeTwoFactor` — full in-memory `TwoFactorPort` adapter | — |
| `tests/test_sca_service_extended.py` | `InMemorySCAStore.delete` + `_verify_otp` pyotp fallback | 6 |
| `tests/test_sca_service_more.py` | `ScaApplicationService` error-code mapping (`invalid_method`, `too_many_active`, `challenge_not_found`, `too_many_attempts`, `resend_rejected`) + lazy singleton | 8 |
| `tests/test_two_factor_more.py` | `TOTPService` ImportError paths + backup-code one-time-use, case-insensitivity, idempotent revoke + `TwoFactorPort` Protocol contract via `FakeTwoFactor` | 15 |
| **TOTAL** | | **29** |

---

## After (full target set)

| Module | Stmts | Miss | Cover | Δ |
|---|---:|---:|---:|---|
| `services/auth/sca_application_service.py` | 48 | 0 | **100 %** | +8 pp |
| `services/auth/sca_service.py` | 130 | 0 | **100 %** | +2 pp |
| `services/auth/two_factor.py` | 112 | 0 | **100 %** | +4 pp |
| `services/auth/two_factor_port.py` | 4 | 0 | **100 %** | ±0 (already 100 %) |
| **TOTAL** | **294** | **0** | **100 %** | — |

**Tests passed (final):** 112 (+29). **Failures:** 0.

Все цели задачи перевыполнены: `sca_service ≥ 80 %`, `sca_application_service ≥ 90 %`, `two_factor ≥ 80 %`, `two_factor_port = 100 %` — фактически достигнуто 100 % по всем четырём модулям.

---

## Canon compliance

| Constraint | Status |
|---|---|
| `api/routers/auth.py` not modified (`git diff main -- api/routers/auth.py` empty) | ✅ |
| No direct BANXE.RAR import | ✅ (нет ни одного нового импорта из `BANXE.RAR`) |
| No port contracts changed (`services/auth/*` untouched) | ✅ |
| Application boundary kept thin — only test-side additions | ✅ |
| Port-fallback path tested via `monkeypatch sys.modules['pyotp'] = None` | ✅ |
| Protocol contract test via in-memory fake adapter (`FakeTwoFactor`) | ✅ |
| `ruff check .` + `ruff format` clean | ✅ |

---

## Outstanding

Нет остаточных missing-lines в перечисленных модулях. Дальнейший рабочий
фокус остаётся на `sprint4/sca-application-boundary` после merge этой ветки.
