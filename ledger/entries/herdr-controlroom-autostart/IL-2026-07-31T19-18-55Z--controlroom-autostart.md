---
il_ts: "2026-07-31T19:18:55Z"
session_id: "herdr-controlroom-autostart"
source: "docs/runbooks/CONTROL-ROOM.md"
status: PROPOSED
il: "IL-OPS-01"
---

# IL-OPS-01 follow-up — Control-Room persistent autostart (runbook append)

Append-only runbook section: operator commands for systemd --user autostart of the
read-only Control-Room (scripts/control-room.sh + herdr-controlroom.service, host-level).
Boundary unchanged per ADR-056/INV-OPS-01: read-only, non-privileged, no engine/DB/midaz
write, no client-instruction path; herdr multiplexer-only. Enable/start = operator (Rule 11).

operator merge required. No numeric mint issued (emi-stack manual IL convention).
