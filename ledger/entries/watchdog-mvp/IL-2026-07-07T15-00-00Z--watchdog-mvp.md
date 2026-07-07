---
il_ts: 2026-07-07T15:00:00Z
session_id: watchdog-mvp
source: agent-factory
status: PROPOSED
---
### Sprint 2 Watchdog MVP skeleton

- **Files:** services/watchdog/watchdog.yaml, services/watchdog/watchdog.py,
  tests/watchdog/test_watchdog.py, services/watchdog/README.md
- **Tests:** 11 (>=8 required)
- **I-27:** may_warm=true; may_restart=false; may_reroute=false; may_evict=false
- **Efficiency probes:** tok/s, hot_latency, cold_start, success_rate, correctness
- **Status:** PROPOSED — operator merge required. No mint issued.
