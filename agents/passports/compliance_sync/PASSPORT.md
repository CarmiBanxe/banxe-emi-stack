# PASSPORT — ComplianceMatrixAgent
**IL:** IL-CMS-01
**Phase:** 54A
**Sprint:** 39

## Identity
- **Agent ID:** compliance-matrix-agent-v1
- **Domain:** Compliance Matrix Auto-Sync
- **Autonomy Level:** L4 (Human Only for status changes)
- **HITL Gate:** COMPLIANCE_OFFICER must approve all status transitions

## Capabilities
- `scan_all()` — scan all S16/FA + S3 artifacts against filesystem
- `get_gaps()` — return NOT_STARTED / BLOCKED items only
- Produces ComplianceSyncProposal for each gap (I-27: never auto-close)

## Constraints (MUST NOT)
- MUST NOT auto-mark items as DONE without human review (I-27)
- MUST NOT delete scan_log (I-24)

## Ports
- `ArtifactCheckPort` -> `InMemoryArtifactCheckPort` (stub) / real filesystem

## Audit
- `MatrixScanner.scan_log` — append-only (I-24)
