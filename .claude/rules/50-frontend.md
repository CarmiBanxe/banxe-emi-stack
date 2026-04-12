# Frontend Rules — BANXE AI BANK
# Rule ID: 50-frontend | Load order: 50
# Created: 2026-04-12 (IL-RETRO-02) | IL-ADDS-01, IL-BIOME-01

## Toolchain

- **Linter + Formatter:** Biome 2.3.0 only — do NOT add ESLint or Prettier.
- **Build:** Vite 5, TypeScript 5.6, React 19.
- **State:** Zustand 5 (global stores); React Query 5 (server state); `useState`/`useReducer` (local UI state).
- **Forms:** react-hook-form 7.
- **Charts:** recharts 2.
- **UI primitives:** class-variance-authority + clsx + tailwind-merge (CVA pattern).

## Biome Configuration

- Config lives at `frontend/biome.json` — do not duplicate settings elsewhere.
- `lineWidth: 120`, double quotes, trailing commas (all), semicolons, LF.
- **Never touch these exclusions — they must stay:**
  - `src/generated/**` — Mitosis auto-generated React output
  - `**/*.lite.tsx` — Mitosis source files (non-standard syntax)

## Mitosis Component Pipeline

- Write once in `src/components/*.lite.tsx` (Mitosis source).
- Generate to `src/generated/*.tsx` (React output) via:
  ```bash
  make generate-component COMPONENT=MyComponent
  ```
- **Never edit `src/generated/` files manually** — they are overwritten on next generate.
- Biome auto-formats generated output via `make generate-component`.
- Import generated components: `import { MyComponent } from "@/generated/MyComponent"`.

## Component Conventions

- All components use CVA pattern for variants:
  ```typescript
  const buttonVariants = cva("base-classes", { variants: { ... } });
  ```
- Props interfaces: `interface ComponentProps { ... }` — never `type`.
- No default exports for components — always named exports.
- Co-locate test with component: `MyComponent.test.tsx` next to `MyComponent.tsx`.

## State Management

- **No prop drilling beyond 2 levels** — use Zustand store.
- Store files: `src/stores/*.store.ts`.
- Store slices: one domain per store (`useAuthStore`, `usePaymentStore`, etc.).
- Derived state: compute in selector, not in component.

## Financial Values in Frontend

- Amounts from API are **strings** (DecimalString). Never treat as numbers.
- Format for display only: `new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(Number(amountStr))`.
- Never send amounts back as numbers — always as strings in API payloads.

## Testing

- Test runner: Vitest + @testing-library/react.
- Coverage: `vitest run --coverage` → artifact uploaded in CI.
- Co-locate test files: `*.test.tsx` or `*.spec.tsx` next to source.
- Mock API calls with `vi.fn()` — never mock Zustand stores directly.

## CI

- Gate 5 in quality-gate.yml: `npx biome ci --reporter=github .` (must pass before merge).
- Vitest runs in `vitest` job (needs: biome).
- See `.github/workflows/lint-frontend.yml` for dedicated frontend workflow.

## References

- Config: `frontend/biome.json`, `frontend/package.json`
- Makefile: `make generate-component COMPONENT=X`
- ADR: `docs/adr/ADR-001-biome-vs-eslint.md`
- Design tokens: managed via Penpot MCP (`sync_design_tokens`)
