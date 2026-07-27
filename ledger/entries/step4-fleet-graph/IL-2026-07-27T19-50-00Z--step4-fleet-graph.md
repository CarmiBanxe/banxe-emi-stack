---
il_ts: 2026-07-27T19:50:00Z
session_id: step4-fleet-graph
source: agent-factory
status: PROPOSED
---
### STEP4: fleet graph + reverse-dependency impact gate (Fable 5 rollout, emi-stack)

- **Instruction:** Build the SQLite fleet graph from STEP3 SCIP artifacts and add
  the reverse-dependency impact gate. Builder scripts/gitnexus/build_fleet_graph.py
  (stdlib+sqlite3; minimal protobuf wire parser — no scip CLI/protoc/new tools;
  repo-relative path normalization; single-writer, fresh DB per run; meta carries
  graph_commit+built_at; targets carry OK/UNKNOWN per NO-MOCK — missing artifact,
  parse failure, zero symbols all = UNKNOWN visible). Gate scripts/gitnexus/
  impact_gate.py: changed files -> defined symbols -> reverse deps -> zones;
  verdicts REPORT / ACK_REQUIRED (cross-zone or CRITICAL; label cross-repo-ack) /
  UNKNOWN (fail-closed-visible); ADVISORY this step (--enforce unused until
  STEP4c/STEP8; I-27). Workflow .github/workflows/fleet-graph.yml: awaits the
  commit's scip-index run, downloads artifacts (gaps => UNKNOWN), builds, gates;
  contexts fleet-graph + impact-gate PRODUCER-ONLY (branch protection untouched).
- **Cross-repo (ADR-117):** config/gitnexus/fleet.crosslink.json — DERIVED
  METADATA ONLY from banxe-architecture org-path-ownership.map.yaml @ 94ce94c
  (S1 ORG-MAP, 0d-room-based): 4 unambiguous zone->room->owner_line joins
  (ledger-core->F2-ledger-room/CFO SMF2; compliance-aml->F3-aml-room/MLRO SMF17;
  safeguarding-recon->F2-safeguarding-room/CFO; reporting-fca->F3-regrep-room/CFO);
  7 zones TODO-operator (NO-MOCK, not guessed). CI never reads the architecture tree.
- **ownership.map.json:** append-only fleet_graph block (db_artifact, single-writer
  builder note, crosslink_file, freshness_slo max_lag_commits=50 with degrade-to-
  structural+ack stale behavior, impact_gate thresholds/ack_label/unknown_rule) +
  extension_points.step4_fleet_graph_status. STEP2/STEP3 fields untouched — all
  four self-checks green (gen_codeowners, scip_manifest, build self-check, gate
  self-test).
- **Files:** .github/workflows/fleet-graph.yml (new, actions SHA-pinned),
  scripts/gitnexus/build_fleet_graph.py (new), scripts/gitnexus/impact_gate.py
  (new), config/gitnexus/fleet.crosslink.json (new, derived),
  config/gitnexus/ownership.map.json (append-only), docs/canon/
  GITNEXUS-STEP4-FLEET-GRAPH.md (new), this shard.
- **Invariants:** I-24 (append-only; this governance-touching PR carries its own
  shard — satisfies guardian-ledger); I-27 (advisory, humans ack); ADR-117
  (derived metadata only); ADR-060/120 (agent/factory/EMISTACK01/step4-fleet-graph
  via dedicated worktree); singleton ledger-PR; Fable 5 (SQLite single-writer
  store, NO-MOCK, freshness explicit, stale=>degrade not blind-block, no god
  server, GitNexus replaceable).
- **Reference:** Fable 5 consultant response §2/§3/§6 roadmap step 4; PR #331/#332/
  #333(STEP2)/#334(STEP3).
- **Status:** PROPOSED — operator merge required. No mint issued.
