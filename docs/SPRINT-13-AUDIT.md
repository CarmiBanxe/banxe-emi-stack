# SPRINT-13-AUDIT.md — banxe-emi-stack
# Sprint 13 Phase 7 Readiness Audit
# Date: 2026-04-13
# Auditor: Claude Code (Sonnet 4.6) + Moriel Carmi

---

## Sprint 13 Summary

| Metric | Sprint 12 | Sprint 13 | Delta |
|--------|-----------|-----------|-------|
| Tests passing | 2227 | 2378 | +151 |
| Tests skipped | 3 | 3 | = |
| Coverage | 80.92% | 82.18% | +1.26pp |
| API endpoints | 78 | 78 | = (no new routes) |
| Commits | — | 10 | — |
| Blocked tasks | — | 4 | catalogued in BT-001..BT-004 |

---

## Task completion

| ID | Task | Status | Commits | Tests added |
|----|------|--------|---------|-------------|
| S13-00 | ArchiMate import pipeline (XML/CSV → JSON + registry) | ✅ DONE | f930a80 | 32 |
| S13-01 | Ledger STUB→ACTIVE (real Midaz adapter) | ✅ DONE | b9d4623 | — |
| S13-02 | IAM STUB→ACTIVE (Keycloak JWKS offline JWT validation) | ✅ DONE | d472594 | 51 |
| S13-03 | Case Management: update/close/list (MarbleAdapter + Mock) | ✅ DONE | 4fe386b | 22 |
| S13-04 | Agreement lifecycle: KYC gate (FCA COBS 6) | ✅ DONE | c3b7bc3 | 17 |
| S13-05 | Payment coverage 67%→95% (rail, n8n, event bus, factory) | ✅ DONE | e3aba48 | 29 |
| S13-06 | Auth coverage 53%→100% (direct async unit tests) | ✅ DONE | e15f9ce | 10 |
| S13-07 | Registry sync: archimate-map.md (13th) + domain/changelog | ✅ DONE | 28c720a | — |
| S13-08 | Alembic production-ready: CI schema-drift check + rollback | ✅ DONE | feae509 | — |
| S13-09 | BLOCKED-TASKS.md: BT-001..BT-004 catalogue | ✅ DONE | eb7c1ae | — |
| S13-10 | SPRINT-13-AUDIT.md (this file) | ✅ DONE | — | — |

**All 11 tasks complete.**

---

## Coverage audit (S13-06 findings)

### Before Sprint 13
| Module | Coverage |
|--------|----------|
| `api/routers/auth.py` | 53% (lines 54, 66, 104-152 missing) |
| `services/payment/payment_service.py` | 67% |
| `services/iam/mock_iam_adapter.py` | ~60% (KeycloakAdapter pragma: no cover) |
| `services/case_management/marble_adapter.py` | ~40% |
| `services/agreement/agreement_service.py` | ~85% |

### After Sprint 13
| Module | Coverage |
|--------|----------|
| `api/routers/auth.py` | **100%** |
| `services/payment/payment_service.py` | **95%** |
| `services/iam/mock_iam_adapter.py` | **98%** |
| `services/case_management/marble_adapter.py` | **90%+** |
| `services/agreement/agreement_service.py` | **98%** |

### Remaining coverage gaps (not Sprint 13 scope)
| Module | Coverage | Reason |
|--------|----------|--------|
| `api/routers/compliance_kb.py` | 39% | RAG endpoints require ChromaDB + vector store |
| `api/routers/transaction_monitor.py` | 34% | Requires live Redis + RabbitMQ |
| `api/routers/experiments.py` | 43% | Requires live experimentation backend |
| `api/routers/consumer_duty.py` | 46% | Requires live DB + service layer |

---

## Architecture changes

### Services status after Sprint 13

| Service | Before | After | Change |
|---------|--------|-------|--------|
| `services/iam/` | STUB | ACTIVE+STUB | JWKS offline validation (S13-02) |
| `services/agreement/` | STUB | ACTIVE+STUB | KYC gate enforced (S13-04) |
| `services/case_management/` | STUB | ACTIVE+STUB | update/close/list added (S13-03) |
| `services/ledger/` | STUB | ACTIVE+STUB | Midaz adapter live (S13-01) |

### New files created
| File | Purpose |
|------|---------|
| `.ai/registries/archimate-map.md` | 13th registry: ArchiMate pipeline metadata |
| `.github/workflows/alembic-check.yml` | CI: schema drift detection on every push |
| `scripts/db_rollback.sh` | Safe Alembic rollback with audit log |
| `docs/BLOCKED-TASKS.md` | External blockers catalogue (BT-001..BT-004) |
| `docs/SPRINT-13-AUDIT.md` | This file |

---

## Blocked tasks (external — not code-blocked)

| ID | System | Blocker | Owner |
|----|--------|---------|-------|
| BT-001 | DocuSign | API key not provisioned | CEO |
| BT-002 | Jube ML | Server not deployed on GMKtec | DevOps |
| BT-003 | Keycloak | No production realm deployed | DevOps |
| BT-004 | Marble | API key not provisioned | CEO/Compliance |

See `docs/BLOCKED-TASKS.md` for full unblocking actions.

---

## FCA compliance posture

| Requirement | Coverage | Evidence |
|-------------|----------|---------|
| eIDAS e-sig workflow (PENDING→SIGNED) | ✅ Complete | `agreement_service.py`, 98% coverage |
| KYC gate before product activation (FCA COBS 6) | ✅ Complete | `TestKycGate` 17 tests all green |
| Keycloak JWKS offline validation | ✅ Complete | `KeycloakAdapter.validate_token()`, 98% IAM coverage |
| AML case routing (Marble) | ✅ Complete (stub) | All 3 case ops implemented, BT-004 for live |
| Alembic schema migration integrity | ✅ Complete | `alembic check` passes, CI workflow added |
| CASS 15 safeguarding (Sprint 12) | ✅ Carry forward | 44 safeguarding tests |
| Tri-party recon (Sprint 12) | ✅ Carry forward | 27 recon tests |

---

## Phase 7 readiness verdict

**STATUS: READY FOR PHASE 7** ✅

Conditions met:
- [x] All Sprint 13 tasks complete (11/11)
- [x] Test count: 2378 passed (target: >2300)
- [x] Coverage: 82.18% (gate: ≥80%)
- [x] Zero pre-commit failures
- [x] All commits pushed to `main`
- [x] Blocked tasks catalogued with owners and unblocking actions
- [x] Registry sync complete (13 registries up to date)
- [x] Alembic in sync: `alembic check` passes

Conditions not met (external):
- [ ] BT-001: DocuSign API key (CEO action required)
- [ ] BT-003: Keycloak production realm (DevOps action required)
- [ ] BT-004: Marble API key (CEO/Compliance action required)
