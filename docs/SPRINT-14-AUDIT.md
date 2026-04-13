# SPRINT-14-AUDIT.md — banxe-emi-stack + banxe-platform
# Sprint 14 — Stub Inventory, E2E Tests, Coverage 87%, PSD2 SCA, Platform Registries
# Date: 2026-04-13
# Auditor: Claude Code (Sonnet 4.6) + Moriel Carmi

---

## Sprint 14 Summary

| Metric | Sprint 13 | Sprint 14 | Delta |
|--------|-----------|-----------|-------|
| Tests passing | 2,378 | 2,619 | +241 |
| Tests skipped | 3 | 2 | -1 |
| Coverage | 82.18% | 87.00% | +4.82pp |
| API endpoints | 78 | 78 | = (no new routes) |
| Integration tests | 0 | 19 | +19 |
| banxe-platform registries | 4 | 12 | +8 |
| banxe-emi-stack registries | 13 | 13 | = (all updated) |
| ROADMAP.md (platform) | — | ✅ Created | Phase 7 IN PROGRESS |

---

## Task Completion

| ID | Task | Scope | Status | Tests added | Coverage Δ |
|----|------|-------|--------|-------------|-----------|
| S14-01 | `docs/STUB-INVENTORY.md` — 41 stub entries | emi-stack | ✅ DONE | — | — |
| S14-02 | `tests/integration/test_e2e_compliance_flow.py` — 19 E2E tests | emi-stack | ✅ DONE | +19 | +~0.5pp |
| S14-03 | Coverage uplift 82.18% → 87.00% | emi-stack | ✅ DONE | +222 | +4.82pp |
| S14-04 | banxe-platform monorepo scaffold verify | platform | ✅ DONE | — | — |
| S14-05 | Design system tokens (colors, typography, spacing, breakpoints) | platform | ✅ DONE | — | — |
| S14-06 | Web app scaffold Next.js 15 verify | platform | ✅ DONE | — | — |
| S14-07 | Mobile app scaffold Expo SDK 53 verify | platform | ✅ DONE | — | — |
| S14-08 | PSD2 SCA stubs — web + mobile + design tokens | platform | ✅ DONE | — | — |
| S14-09 | 8 new banxe-platform registries (total 12) | platform | ✅ DONE | — | — |
| S14-10 | All 13 banxe-emi-stack registries updated | emi-stack | ✅ DONE | — | — |
| S14-11 | `ROADMAP.md` — banxe-platform Phase 7 IN PROGRESS | platform | ✅ DONE | — | — |
| S14-12 | `docs/SPRINT-14-AUDIT.md` (this file) | emi-stack | ✅ DONE | — | — |

**All 12 tasks complete.** ✅

---

## Coverage Uplift Detail (S14-03)

Starting baseline: **82.18%** (2378 tests)
Final: **87.00%** (2619 tests)

| Test file | Tests | Lines covered | Module → coverage |
|-----------|-------|---------------|-------------------|
| `tests/test_two_factor.py` (overwritten) | 30 | ~112 | `services/two_factor/totp_service.py` 0% → ~95% |
| `tests/test_reasoning_bank.py` (new) | 26 | ~238 | `services/reasoning_bank/` 0% → ~90% |
| `tests/test_markdown_parser.py` (new) | 22 | ~47 | `services/compliance_kb/markdown_parser.py` 25% → ~95% |
| `tests/test_repo_watch.py` (new) | 35 | ~395 | `services/repo_watch/` 0% → ~85% |
| `tests/test_config_modules.py` (new) | 21 | ~57 | Various config modules 0% → 100% |
| `tests/test_api_health.py` (extended) | +2 | ~4 | Health readiness error paths |
| `tests/test_experiment_copilot/test_experiment_store.py` (extended) | +3 | ~8 | `ExperimentStore.delete()` |
| `tests/integration/test_e2e_compliance_flow.py` (new) | 19 | ~200 | KYC, agreement, case management flows |

---

## E2E Integration Tests (S14-02)

19 tests in `tests/integration/test_e2e_compliance_flow.py`:

| # | Test | Flow |
|---|------|------|
| 1 | KYC standard approval | PENDING → DOCUMENT_REVIEW → APPROVED |
| 2 | KYC EDD/MLRO path | PEP flag → MLRO_REVIEW → APPROVED |
| 3 | KYC rejection | Sanctions hit → REJECTED |
| 4 | Agreement KYC gate blocks | PENDING status → sign rejected |
| 5 | Agreement KYC gate passes | APPROVED → ACTIVE |
| 6 | T&C supersede | New version → re-sign required |
| 7 | Case OPEN→RESOLVED | Full resolution flow |
| 8 | Case OPEN→CLOSED | Manual close |
| 9 | Case list/filter | Filter by status |
| 10 | HIGH risk TX → case | Transaction monitoring case creation |
| 11 | Full onboarding pipeline | KYC→Agreement→Sign→ACTIVE |
| 12 | Full onboarding pipeline rejected | KYC rejected → sign blocked |
| 13 | Multi-product agreements | e-money + FX |
| 14 | CRITICAL case priority | Highest priority handling |
| 15 | KYC get_workflow | Returns state |
| 16 | KYC get_workflow unknown | Returns None |
| 17-19 | MLRO EDD full flow | EDD trigger → MLRO review → approve → sign |

All 19 tests: **PASS** ✅ (no external dependencies, InMemory adapters only)

---

## PSD2 SCA Stubs (S14-08)

### Web Component: `packages/web/src/components/molecules/SCAChallenge.tsx`

| Feature | Implementation | Status |
|---------|---------------|--------|
| Dialog accessibility | `role="dialog"`, `aria-modal`, `aria-labelledby`, `aria-describedby` | ✅ |
| OTP input | `inputMode="numeric"`, `autoComplete="one-time-code"`, `maxLength={6}` | ✅ |
| Biometric | WebAuthn stub (placeholder response) | 🔶 STUB |
| Error display | `role="alert"` | ✅ |
| PSD2 regulatory footer | `PSD2 Art.97 SCA · Banxe EMI FRN 900000` | ✅ |
| States | prompt → otp_entry \| submitting → error \| success | ✅ |

### Mobile Screen: `packages/mobile/app/sca/index.tsx`

| Feature | Implementation | Status |
|---------|---------------|--------|
| Biometric | expo-local-authentication `authenticateAsync()` | ✅ |
| Haptics | expo-haptics `NotificationFeedbackType.Success/Error` | ✅ |
| Keyboard avoidance | `KeyboardAvoidingView` (Platform.OS iOS/Android) | ✅ |
| OTP input | `textContentType="oneTimeCode"`, numeric pad, `maxLength={6}` | ✅ |
| Navigation | `useLocalSearchParams`, `router.back()` | ✅ |
| Accessibility | `accessibilityRole`, `accessibilityState`, `accessibilityLabel` | ✅ |
| Biometric POST | POST biometric proof to `/auth/sca` | 🔶 STUB |

### Design Tokens (S14-05)

| File | Contents | Key values |
|------|----------|-----------|
| `colors.ts` | 30+ color tokens | primary=#1A1A2E, accent=#00C6AE (4.8:1 WCAG AA) |
| `typography.ts` | 5 font sizes, 6 weights | xs=12px → 5xl=48px, Inter/Roboto |
| `spacing.ts` | 4pt grid + semantic | touchTarget=44px, inputHeight=48px |
| `breakpoints.ts` | Mobile-first + zIndex | sm=640px, modal z-index=400 |

---

## banxe-platform Registries Created (S14-09)

| Registry | Purpose |
|----------|---------|
| `tokens-map.md` | Design token reference (colors, typography, spacing, breakpoints) |
| `sca-map.md` | PSD2 SCA flow — web modal + mobile screen + backend integration |
| `auth-map.md` | Auth flow — login, SCA, session management, route protection |
| `types-map.md` | TypeScript type catalogue — all shared types documented |
| `store-map.md` | Zustand store documentation — state shape + actions |
| `api-map.md` | Frontend API client — all methods, endpoints, error handling |
| `integration-map.md` | emi-stack integration contract — endpoint mapping, CORS, env vars |
| `compliance-map.md` | FCA/PSD2 regulatory feature matrix + WCAG compliance |

Total: **12 registries** (4 existing + 8 new)

---

## Stub Inventory Summary (S14-01)

`docs/STUB-INVENTORY.md` catalogues **41 stubs** across 5 parts:

| Part | Domain | Entries | Key blocker |
|------|--------|---------|------------|
| 1 — Compliance | AML, KYC, Fraud, Case Mgmt | 12 | BT-001 (DocuSign/CEO) |
| 2 — Banking Core | Ledger, Payment, Recon, Reporting | 10 | BT-002 (Midaz/DevOps) |
| 3 — Infrastructure | IAM, Notifications, Events | 8 | BT-003 (Keycloak/DevOps) |
| 4 — Frontend Platform | SCA biometric, token refresh, inactivity | 7 | BT-004 (Marble/CEO) |
| 5 — Test Pragmas | `# noqa`, `type: ignore`, `pragma: no cover` | 4 | — |

---

## Acceptance Criteria Verification

| Criterion | Target | Actual | Pass |
|-----------|--------|--------|------|
| All 12 tasks complete | 12/12 | 12/12 | ✅ |
| Test coverage | ≥ 87% | 87.00% | ✅ |
| Tests passing | ≥ 2,650 | 2,619 | ⚠️ |
| Integration tests | ≥ 15 | 19 | ✅ |
| Stub inventory entries | ≥ 20 | 41 | ✅ |
| banxe-platform registries | 12 | 12 | ✅ |
| Pre-commit failures | 0 | 0 | ✅ |

> ⚠️ Tests: target was ≥ 2,650 — actual is 2,619 (31 short). Recommend adding ~35 additional tests in Sprint 15
> to pass the gate, or adjusting the threshold to ≥ 2,600 (coverage gate at 87% is met).

---

## Sprint 15 Priorities

| Priority | Task | Rationale |
|----------|------|-----------|
| 1 | Wire SCA modal in transfers page (web) | Closes PSD2 Art.97 end-to-end |
| 2 | Wire SCA screen in mobile transfers | Closes PSD2 Art.97 mobile end-to-end |
| 3 | WebAuthn full implementation (web) | Remove biometric stub |
| 4 | POST biometric proof to /auth/sca (mobile) | Remove mobile biometric stub |
| 5 | Tests: +35 to reach ≥ 2,650 | Pass acceptance criterion |
| 6 | Playwright E2E web tests (≥ 10) | Non-regression gate |
| 7 | PSD2 RTS Art.10 token refresh | Inactivity timer + silent refresh |

---

*Audit signed off: 2026-04-13 | Claude Code Sonnet 4.6 + Moriel Carmi*
