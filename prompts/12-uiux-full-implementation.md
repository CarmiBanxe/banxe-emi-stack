# PROMPT 12 — UI/UX FULL IMPLEMENTATION
## For: Claude Code on Legion (BANXE AI BANK)
## Ticket: IL-UI-01 | Phase 7
## Run AFTER: Phases 5-6 complete (Recon + MCP)

---

## ROLE

You are a Senior Full-Stack AI Implementation Engineer for BANXE AI BANK.
Task: Build production-grade web + mobile UI/UX monorepo `banxe-platform/`
using open-source stack, integrated with existing `banxe-emi-stack` backend.

## CONTEXT

Backend repo: `/home/mmber/banxe-emi-stack` (Python/FastAPI, 80+ endpoints)
New frontend repo: `/home/mmber/banxe-platform` (TypeScript monorepo)
Branch: `main`
Backend API: `http://localhost:8000/v1/`

### Existing Backend Endpoints (from banxe-emi-stack)
- Auth: POST /v1/auth/login
- Accounts: GET/POST /v1/accounts, GET /v1/accounts/{id}/balance
- Transactions: GET/POST /v1/transactions, POST /v1/transactions/{id}/approve
- KYC: POST /v1/kyc/submit, GET /v1/kyc/status
- AML: GET /v1/aml/screening/{id}
- Compliance: GET /v1/compliance/dashboard
- Statements: GET /v1/statements
- Reconciliation: GET /v1/recon/status, POST /v1/recon/run
- MCP: http://localhost:9100/mcp (28 tools)

---

## PHASE 1 — MONOREPO SCAFFOLD

```bash
cd /home/mmber
mkdir banxe-platform && cd banxe-platform
git init
pnpm init

cat > pnpm-workspace.yaml << 'EOF'
packages:
  - 'packages/*'
EOF

cat > turbo.json << 'EOF'
{
  "$schema": "https://turbo.build/schema.json",
  "globalDependencies": ["**/.env.*local"],
  "pipeline": {
    "build": { "dependsOn": ["^build"], "outputs": [".next/**", "dist/**"] },
    "dev": { "cache": false, "persistent": true },
    "lint": {},
    "test": { "dependsOn": ["build"] },
    "typecheck": { "dependsOn": ["^build"] }
  }
}
EOF

mkdir -p packages/shared/src packages/web packages/mobile
```

### Verification:
- `ls packages/` shows shared/ web/ mobile/
- `cat pnpm-workspace.yaml` correct
- `cat turbo.json` valid JSON

---

## PHASE 2 — SHARED DESIGN SYSTEM (packages/shared)

Create `packages/shared/src/design-tokens.ts`:
- colors: primary=#1A2B6B, accent=#00C6AE, bg=#F5F7FA, surface=#FFFFFF, text=#1A1A2E, error=#DC2626, success=#16A34A, warning=#F59E0B
- typography: Inter (headings), Roboto (body), size scale 12-48
- spacing: 4-point grid (4,8,12,16,24,32,48,64)
- borderRadius: sm=4, md=8, lg=16, pill=9999
- shadows: card, modal, button
- state colors: hover, active, disabled

Create `packages/shared/src/types/`:
- `api.ts` — API response types matching backend Pydantic models
- `auth.ts` — AuthUser, LoginRequest, TokenResponse
- `account.ts` — Account, Balance, Transaction
- `kyc.ts` — KYCSubmission, KYCStatus
- `compliance.ts` — ComplianceDashboard, AMLScreening

Create `packages/shared/src/api-client.ts`:
- Typed fetch wrapper for banxe-emi-stack API
- Base URL configurable via env
- Token-based auth header injection
- Error handling with typed responses

Create `packages/shared/src/store/`:
- Zustand stores: authStore, accountStore, transactionStore
- Shared across web and mobile

### Verification:
- `npx tsc --noEmit` passes in packages/shared
- All types exported from index.ts

---

## PHASE 3 — WEB APPLICATION (packages/web)

```bash
cd packages/web
pnpm create next-app . --typescript --tailwind --eslint --app --src-dir --import-alias "@/*"
pnpm add @workspace/shared zustand
pnpm add -D tailwindcss@latest
npx shadcn@latest init
```

Create pages:
1. `src/app/auth/login/page.tsx` — Email + PIN login, calls POST /v1/auth/login
2. `src/app/dashboard/page.tsx` — Account balance cards, last 5 transactions, quick actions
3. `src/app/transfers/page.tsx` — IBAN input, amount, PSD2 SCA 2-step confirmation flow
4. `src/app/transactions/page.tsx` — Full transaction history with filters
5. `src/app/kyc/page.tsx` — Document upload, liveness check placeholder
6. `src/app/compliance/page.tsx` — Compliance dashboard (FCA status, recon status)
7. `src/app/settings/page.tsx` — Profile, security, biometric toggle
8. `src/app/statements/page.tsx` — Statement list + PDF download

Create components (Atomic Design):
- atoms/: Button, Input, Badge, Icon, Skeleton
- molecules/: Card, TransactionRow, AccountSelector, StatusBadge
- organisms/: DashboardHeader, TransferForm, TransactionList, CompliancePanel
- layout/: Sidebar, TopNav, MobileNav, AuthGuard

Constraints:
- shadcn/ui components
- Tailwind CSS v4 with design tokens from shared
- WCAG 2.1 AA (ARIA labels, keyboard nav, contrast ratios)
- Session timeout modal (5-minute warning)
- GDPR + PSD2 consent screens
- No raw card numbers displayed
- Mobile-first responsive (320px-1440px)

Create `packages/web/CLAUDE.md`

### Verification:
- `pnpm dev` starts on :3001
- All pages render without errors
- Login flow -> Dashboard navigation works

---

## PHASE 4 — MOBILE APPLICATION (packages/mobile)

```bash
cd packages/mobile
npx create-expo-app . --template tabs
pnpm add nativewind tailwindcss react-native-reanimated
pnpm add @gluestack-ui/themed zustand
pnpm add expo-local-authentication expo-secure-store
pnpm add @workspace/shared
```

Create screens:
1. `app/auth/onboarding.tsx` — 3 animated slides (Reanimated 3)
2. `app/(tabs)/dashboard.tsx` — Balance card, 5 recent transactions, quick actions
3. `app/(tabs)/transfers.tsx` — IBAN input, amount, PSD2 SCA biometric confirmation
4. `app/(tabs)/transactions.tsx` — Transaction list with pull-to-refresh
5. `app/kyc/index.tsx` — Document camera capture, selfie, liveness check
6. `app/(tabs)/settings.tsx` — Biometric toggle, security, profile
7. `app/cards/index.tsx` — Card management (masked numbers)

Constraints:
- NativeWind (Tailwind for RN) with shared tokens
- Reanimated 3 for all animations (never Animated API)
- SafeAreaView from react-native-safe-area-context
- expo-local-authentication for biometric
- expo-secure-store for token storage
- Haptic feedback on key actions
- Skeleton loaders for async data
- Certificate pinning enabled

Create `packages/mobile/CLAUDE.md`

### Verification:
- `npx expo start` launches
- All tabs render
- Navigation between screens works

---

## PHASE 5 — CLAUDE.MD + SKILLS

Create root `CLAUDE.md` with: architecture, rules, backend API, brand tokens.

Create `.claude/skills/banxe-ui-bootstrap.md`: UI scaffold generation workflow.

---

## PHASE 6 — REGISTRIES + INTELLIGENCE

Create `.ai/registries/`: ui-map.md, web-map.md, mobile-map.md, shared-map.md
Create `.ai/reports/`: ui-build-readiness.md, mobile-web-gap-analysis.md

---

## PHASE 7 — INTEGRATION TESTS

Web tests: auth, dashboard, transfers, compliance
Mobile tests: auth, dashboard, transfers

Verification: `pnpm test` passes, coverage >= 60%

---

## PHASE 8 — GIT + COMMIT

```bash
cd /home/mmber/banxe-platform
git add -A
git commit -m "feat(ui): Phase 7 UI/UX platform scaffold — web + mobile + shared [IL-UI-01]"
git remote add origin git@github.com:CarmiBanxe/banxe-platform.git
git push -u origin main
```

---

## INFRASTRUCTURE UTILIZATION CHECKLIST (CANON)

| # | Component | Used | Where |
|---|-----------|------|-------|
| 1 | Semgrep SAST | Must add | .semgrep/typescript-banking.yml |
| 2 | n8n workflows | Must add | UI deploy notification |
| 3 | Docker | Must add | docker/web.Dockerfile |
| 4 | Grafana | Must add | Frontend metrics dashboard |
| 5 | MCP tools | API consumer | Uses banxe_mcp via API |
| 6 | CLAUDE.md | Must create | Root + per-package |
| 7 | .ai/registries | Must create | ui-map, web-map, mobile-map |
| 8 | Soul prompt | Must reference | .ai/soul.md |

---

## SUCCESS CRITERIA

- [ ] Monorepo builds: `pnpm build` succeeds
- [ ] Web: 8 pages render, login works, PSD2 flow works
- [ ] Mobile: 7 screens render, biometric works, navigation works
- [ ] Shared: Types match backend, API client works, stores functional
- [ ] Tests: >= 20 tests pass
- [ ] CLAUDE.md: 3 files (root, web, mobile)
- [ ] Registries: 4 files in .ai/registries/
- [ ] Reports: 2 files in .ai/reports/
- [ ] Infrastructure Checklist: All applicable items addressed
- [ ] Git: Clean commit with conventional format

---

*Created: 2026-04-11 by Perplexity Computer*
*For execution: `cat prompts/12-uiux-full-implementation.md` then paste to Claude Code*
