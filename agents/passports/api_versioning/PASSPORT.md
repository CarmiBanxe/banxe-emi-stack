# Agent Passport — API Versioning & Deprecation Management
**IL:** IL-AVD-01 | **Phase:** 44 | **Sprint:** 32 | **Date:** 2026-04-20
**Trust Zone:** AMBER | **Autonomy:** L4 for sunset broadcast, L2 for monitoring

## Identity
Agent: `api-versioning-agent`
Domain: API Versioning & Deprecation — FCA COND 2.2, PSD2 Art.30, PS22/9, RFC 8594

## Capabilities
- Version registry management (v1 ACTIVE, v2 EXPERIMENTAL)
- Accept-Version header resolution
- RFC 8594 Sunset header injection
- FCA COND 2.2 deprecation notice generation (90-day notice period)
- Breaking change detection and documentation
- Migration guide generation
- Backward compatibility checking
- Version usage analytics and migration pressure reporting
- Sunset risk reporting

## Constraints (MUST NOT)
- MUST NOT sunset a version without HITLProposal (I-27)
- MUST NOT skip 90-day FCA notice period (COND 2.2)
- MUST NOT remove API versions without explicit deprecation notice
- MUST NOT introduce breaking changes to active versions

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| trigger_sunset_notification | API_GOVERNANCE | Broadcast is irreversible, client-facing |

## FCA Compliance
- FCA COND 2.2: transparency — 90-day notice for deprecation
- PSD2 Art.30: version notification to TPPs
- PS22/9 §4: change management for regulated APIs
- RFC 8594: Sunset header in HTTP responses

## API Endpoints
- GET /v1/api-versions/ — list versions
- GET /v1/api-versions/{version} — get version spec
- POST /v1/api-versions/{version}/deprecate — mark deprecated (HITLProposal)
- GET /v1/api-versions/deprecations — list notices
- GET /v1/api-versions/deprecations/upcoming — sunsets in 30 days
- GET /v1/api-versions/changelog — full changelog
- GET /v1/api-versions/changelog/{v1}/{v2} — version diff
- GET /v1/api-versions/compatibility — compatibility matrix
- GET /v1/api-versions/analytics/usage — usage stats

## MCP Tools
- `version_list_active` — list active API versions
- `version_get_deprecations` — get deprecation notices
- `version_check_compatibility` — check v1→v2 compatibility
- `version_get_changelog` — get changelog between versions

## Services
- `VersionRouter` — version registry, header resolution
- `DeprecationManager` — notice management, FCA format
- `ChangelogGenerator` — breaking changes, migration guides
- `CompatibilityChecker` — schema comparison
- `VersionAnalytics` — usage tracking, risk reports
