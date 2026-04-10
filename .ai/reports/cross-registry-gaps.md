# Cross-Registry Gap Report — banxe-emi-stack
# Source: All 12 registries in .ai/registries/
# Created: 2026-04-10 (Phase 5 intelligence pass)
# Migration Phase: 5
# Purpose: Inconsistencies found during cross-reference analysis

## Gaps found and corrected in Phase 5

### GAP-01: Environment variable count mismatch [CORRECTED]
- **File**: `.ai/registries/shared-map.md`
- **Issue**: Stated 30 env vars, actual count from `.env.example` is 32
- **Root cause**: PSD2 category (PSD2_POSTGRES_USER, PSD2_POSTGRES_PASSWORD) was not counted. Bank statement IBANs were grouped under "IBANs" without explicit per-variable listing.
- **Fix**: Updated shared-map.md — added PSD2 category, expanded IBAN variables, corrected total to 32
- **Status**: CORRECTED

### GAP-02: API paths missing /v1/ prefix [CORRECTED]
- **File**: `.ai/registries/api-map.md`
- **Issue**: Phase 4 api-map.md listed paths without the `/v1/` prefix applied by `main.py` via `app.include_router(..., prefix="/v1")`. For example, listed `/customers` instead of `/v1/customers`.
- **Also**: Some endpoints used generic placeholders like `POST /customers/{id}/...` instead of exact path `POST /v1/customers/{customer_id}/lifecycle`
- **Also**: HITL router paths were `proposals` in Phase 4 but actual code uses `queue` (e.g., `/v1/hitl/queue` not `/v1/hitl/proposals`)
- **Fix**: Complete rewrite of api-map.md with all 42 exact paths extracted from router source code, router prefix table showing which routers get /v1 prefix vs router-level prefix
- **Status**: CORRECTED

### GAP-03: Placeholder registry files [CORRECTED]
- **Files**: `ui-map.md`, `web-map.md`, `mobile-map.md`
- **Issue**: Phase 4 created these as minimal placeholders with basic gap tables. No screen inventory, no endpoint mapping, no architecture analysis.
- **Fix**: All three rewritten with comprehensive content:
  - ui-map.md: 28 candidate screens mapped to 42 endpoints, coverage matrix, 5 uncovered gaps identified
  - web-map.md: Two-app strategy (Ops Console + Customer Portal), full page trees with endpoint mapping, auth integration plan, recommended tech stack
  - mobile-map.md: Screen tree, 14-endpoint mobile subset mapping, security considerations, timeline estimate
- **Status**: CORRECTED

### GAP-04: Reporting/SAR endpoints undercounted
- **File**: `.ai/registries/api-map.md`
- **Issue**: Phase 4 listed `POST /reporting/...` as "Additional reporting endpoints (3)" without specifics. Actual count is 9 reporting endpoints with exact paths.
- **Fix**: api-map.md now lists all 9: fin060/generate, fin060/submit, sar (POST+GET), sar/stats, sar/{id} (GET), sar/{id}/approve, sar/{id}/submit, sar/{id}/withdraw
- **Status**: CORRECTED

### GAP-05: Consumer duty endpoints undercounted
- **File**: `.ai/registries/api-map.md`
- **Issue**: Phase 4 listed 3 named endpoints + "Additional endpoint" placeholder. Actual count is 5 with exact paths.
- **Fix**: api-map.md now lists all 5: vulnerability (POST), vulnerability/{customer_id} (GET), fair-value (POST), outcomes (POST), report (POST)
- **Status**: CORRECTED

## Cross-references verified (no gaps found)

| Registry pair | Check | Result |
|--------------|-------|--------|
| api-map.md ↔ service-map.md | 42 endpoints match 22 service modules | ✅ Consistent |
| api-map.md ↔ test-map.md | All routers have test coverage in 46 test files | ✅ Consistent |
| shared-map.md ↔ infra-map.md | Database ports/engines match | ✅ Consistent |
| keycloak-map.md ↔ api-map.md | 7 roles match auth annotations | ✅ Consistent |
| agent-map.md ↔ service-map.md | 9 agents map to compliance services | ✅ Consistent |
| dependency-map.md ↔ api-map.md | FastAPI version matches | ✅ Consistent |
| ui-map.md ↔ web-map.md ↔ mobile-map.md | Screen counts and endpoint references aligned | ✅ Consistent (post Phase 5 rewrite) |

## Outstanding items (not gaps — future work)

| Item | Notes |
|------|-------|
| Role-to-endpoint enforcement | Keycloak roles defined but per-endpoint auth decorators not yet added to all routers |
| OpenAPI spec completeness | Swagger auto-generates but response schemas not fully annotated on all endpoints |
| Test coverage per endpoint | test-map.md counts 995 tests across 46 files but per-endpoint coverage % not calculated |

---
*Last updated: 2026-04-10 (Phase 5 system intelligence pass)*
