---
il_ts: "2026-07-31T21:22:57Z"
session_id: "herdr-controlroom-panes"
source: "scripts/control-room.sh"
status: PROPOSED
il: "IL-OPS-01"
---

# IL-OPS-01 — p4/p5 live read-only panes

p4/p5 panes made live read-only (HTTP-health + TCP reachability; no docker, no creds;
:8000/health avoided due to 401). RED-ZONE recon note. Also surgically removed the two
forbidden endpoints (:8000/health 401, :8000/v1/monitor/health 404) from p2 engine-services
per the same constraint (banxe-api -> TCP; app-health via banxe-mcp :8100). No numeric mint.
