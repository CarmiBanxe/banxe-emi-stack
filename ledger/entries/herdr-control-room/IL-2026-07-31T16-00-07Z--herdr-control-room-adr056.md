---
il_ts: "2026-07-31T16:00:07Z"
session_id: "herdr-control-room-adr056"
source: "docs/adr/ADR-056-herdr-control-room.md"
status: PROPOSED
il: "IL-OPS-01"
---

# IL-OPS-01 — herdr Control Room (Option B, read-only observability)

Governance shard for ADR-056 + docs/runbooks/CONTROL-ROOM.md + INV-OPS-01.
Boundary: herdr multiplexer-only (socket API off, plugins off); read-only; non-privileged OS user; no engine/DB/midaz write path.

operator merge required. No numeric mint issued (emi-stack manual IL convention).
