# ADR-001: Biome 2.3.0 as Frontend Linter/Formatter (replacing ESLint + Prettier)

**Date:** 2026-04-12
**Status:** Accepted
**IL:** IL-BIOME-01 (IL-072)
**Author:** Moriel Carmi / Claude Code

---

## Context

The frontend (`frontend/`) uses React 19 + TypeScript 5.6 + Vite 5.  
Previously the project had no frontend linter configured (eslint scripts were placeholders in `package.json`).

Requirements for the frontend quality gate:
1. Fast enough to run as a pre-commit hook without blocking developers
2. Single tool for linting **and** formatting (avoid Prettier + ESLint coordination overhead)
3. First-class TypeScript/JSX support
4. JSON linting (for `*.config.json`)
5. Compatible with the Mitosis code-generation pipeline — must be able to **exclude** generated files without coupling the linter to build artefacts
6. GitHub Actions integration with SARIF / GitHub annotations

Additionally, the project uses Mitosis CLI to generate React components from `.lite.tsx` source files. These generated files (`src/generated/`) and the source files (`**/*.lite.tsx`) must be excluded from linting, as:
- Generated files contain auto-formatted code that may not match project style
- `.lite.tsx` files use Mitosis-specific syntax that is not valid standard TSX

---

## Decision

**Use Biome 2.3.0** (formerly Rome) as the single frontend linting + formatting tool.

ESLint + Prettier are **not** adopted.

---

## Rationale

| Criterion | Biome 2.3.0 | ESLint + Prettier |
|-----------|------------|-------------------|
| Speed | Rust-native, ~35x faster than ESLint | Node.js, slower at scale |
| Single tool | Yes (lint + format in one binary) | No (two tools, config coordination) |
| TypeScript support | Built-in, no `@typescript-eslint` needed | Requires `@typescript-eslint` plugin chain |
| JSON linting | Built-in | Requires separate plugin |
| `files.ignore` glob | `src/generated/**`, `**/*.lite.tsx` | `ignorePatterns` (less ergonomic) |
| Pre-commit hook | `npx biome check --apply .` | Separate `eslint --fix` + `prettier --write` |
| GitHub Actions | `biomejs/setup-biome@v2` + `--reporter=github` | Custom eslint-annotate action needed |
| Zero config for basic rules | Recommended rules built-in | Requires plugin configuration |

The primary driver is **operational simplicity**: one binary, one config file, one pre-commit step, one CI job. For a fintech backend-heavy repo, minimising frontend toolchain maintenance cost is the correct trade-off.

---

## Consequences

### Positive
- Pre-commit hook runs in < 2s on the frontend directory
- CI biome job is independent of vitest (parallel)
- `biome ci --reporter=github` produces inline PR annotations
- `make generate-component COMPONENT=X` auto-formats Mitosis output through Biome

### Negative / Risks
- Biome rule coverage is narrower than the ESLint ecosystem (no custom FCA-specific rules)
- Biome 2.x is relatively new — potential breaking changes in minor versions
- Developers unfamiliar with Biome may need onboarding

### Mitigations
- Biome version is pinned: `"@biomejs/biome": "2.3.0"` in `package.json` devDependencies
- `$schema` in `biome.json` points to `https://biomejs.dev/schemas/2.3.0/schema.json` — explicit version reference
- If ESLint custom rules become necessary (e.g., FCA-specific TSX patterns), they can be added as a separate `eslint` step targeting only `src/compliance/**` without replacing Biome

---

## Configuration

**`frontend/biome.json`** — key settings:

```json
{
  "formatter": { "lineWidth": 120, "indentStyle": "space", "indentWidth": 2 },
  "javascript": {
    "formatter": { "quoteStyle": "double", "trailingCommas": "all", "semicolons": "always" }
  },
  "files": {
    "include": ["src/**", "*.json", "*.config.ts", "*.config.js"],
    "ignore": [
      "dist/**", "node_modules/**",
      "src/generated/**",
      "**/*.lite.tsx",
      "coverage/**"
    ]
  }
}
```

**Exclusion rules (non-negotiable):**
- `src/generated/**` — Mitosis React output; linting this would create false positives and slow the pipeline
- `**/*.lite.tsx` — Mitosis source syntax is not valid standard TSX; Biome parser would error

---

## Alternatives Considered

### 1. ESLint 9 flat config + Prettier
Rejected because: two-tool coordination overhead, slower CI, more dependencies to maintain.

### 2. Biome + ESLint hybrid
Rejected because: adds back the coordination complexity we are trying to avoid. Revisit if FCA-specific TSX lint rules become mandatory.

### 3. oxlint (Rust-based ESLint-compatible)
Considered but rejected in favour of Biome because Biome includes formatting (oxlint is lint-only) and has better JSON support.

---

## References

- `frontend/biome.json`
- `frontend/package.json` — devDependencies, scripts
- `.pre-commit-config.yaml` — biome-check-frontend local hook
- `.github/workflows/lint-frontend.yml` — biome + vitest CI workflow
- `.github/workflows/quality-gate.yml` — 5-parallel-job refactor
- `Makefile` — `generate-component` target
- IL-072 in `banxe-architecture/INSTRUCTION-LEDGER.md`
