# INSTRUCTION LEDGER — banxe-emi-stack

## IL-LINT-01 — Ruff + Biome + Bandit + MyPy Canon Infrastructure
- Status: DONE
- Proof commit: 1c75213 (baseline)
- Scope: infrastructure only
- Artifacts: pyproject.toml [tool.ruff], frontend/biome.json schema 2.3.0, .pre-commit-config.yaml, .github/workflows/lint-*.yml + quality-gate.yml

## IL-LINT-02 — Bandit Nosec Rationale + gitignore Hardening
- Status: DONE
- Proof commit: b83fb8f
- Scope:
  - nosec B310 provider_registry (scheme-validated)
  - nosec B108 regdata_return (stub, tracked by IL-FIN060-REAL-01)
  - nosec B104 safeguarding-engine (container-internal bind)
  - .gitignore: node_modules, caches
  - mypy installed in .venv

## IL-LINT-03 — Quality Baseline Remediation (OPEN)
- Status: TODO
- Deferred: B017, SIM300, defusedxml B314 (behaviour diff in test_camt053_parser)
- Out-of-scope artefacts (not in IL-LINT): audit/recon/reporting fichi, feat/auth-ports-formalization

---

### IL-LINT-03 — B314 defusedxml + B017 FrozenInstanceError + I001
- Status: OPEN
- Scope:
  - services/batch_payments/file_parser.py
  - tests/test_card_issuing/test_models.py
  - tests/test_multi_currency/test_models.py
- Ready:
  - B314: xml.etree.ElementTree -> defusedxml.ElementTree (ET.fromstring, ET.ParseError)
  - B017: pytest.raises(Exception) -> pytest.raises(FrozenInstanceError) in frozen-dataclass tests
  - I001: import order normalized in both test files
  - ruff scoped: PASS
  - py_compile scoped: PASS
  - bandit targeted: B314 clean on file_parser.py
  - pytest targeted: 44/44 passed (no-cov on the two test_models.py)
  - repo coverage: 42.46% (gate 35%)
- Proof: NO COMMIT YET (pre-commit pytest-fast blocked by out-of-scope tests)
- Blocked-by:
  - IL-CNS-AUD-PIPELINE-FIX
  - IL-OBS-MCP-TESTS-FIX
- Handoff: /tmp/banxe_handoff_2026-04-22_1613.md
- Logs: /tmp/il_lint_03_finalize.log, /tmp/il_lint_03_finalize_scope.log, /tmp/il_lint_03_blocker_report.txt

### IL-CNS-AUD-PIPELINE-FIX — Fix consent/audit integration pipeline test under pytest-fast
- Status: TODO
- Scope:
  - tests/test_integration/test_consent_audit_pipeline.py::TestConsentAuditPipeline::test_query_audit_log_by_event_type
- Owner scope: consent/audit integration (IL-CNS-01 / IL-PGA-01 family)
- Goal: restore passing under global pytest-fast hook without changing observable
  behaviour of consent engine / pgAudit query layer; most likely a fixture or
  event-type filter contract drift.
- Blocks: IL-LINT-03 commit proof

### IL-OBS-MCP-TESTS-FIX — Fix observability MCP tools tests under pytest-fast
- Status: TODO
- Scope:
  - tests/test_observability/test_mcp_tools_observability.py (full test id to be
    recovered from pytest-fast log in next session)
- Owner scope: observability MCP tools (new scope, untracked services/observability/)
- Goal: make the failing test(s) green under pytest-fast; verify that the
  observability scope (routers/observability.py, services/observability/*,
  agents/passports/observability/*) does not regress other suites.
- Blocks: IL-LINT-03 commit proof

---

### IL-COMPSYNC-0X — Compliance Sync scope (parking)
- Status: TODO
- Scope:
  - services/compliance_sync/
  - tests/test_compliance_sync/
- Origin: new untracked in banxe-emi-stack working tree (not part of IL-LINT-03)
- Goal: formalize compliance_sync as its own IL (design + tests + passport);
  promote to DONE only with dedicated proof SHA.

### IL-FRAUDTRACE-0X — Fraud Tracer scope (parking)
- Status: TODO
- Scope:
  - services/fraud_tracer/
  - tests/test_fraud_tracer/
- Origin: new untracked in banxe-emi-stack working tree (not part of IL-LINT-03)
- Goal: formalize fraud_tracer as its own IL; no mixing with IL-LINT-03 or
  IL-FRAUD adapters.

### IL-MIDAZMCP-0X — Midaz MCP scope (parking)
- Status: TODO
- Scope:
  - services/midaz_mcp/
  - tests/test_midaz_mcp/
- Origin: new untracked in banxe-emi-stack working tree
- Goal: formalize midaz_mcp integration as its own IL with Midaz ledger
  contracts and MCP tools passports.

### IL-SCA-ADAPTERS-0X — SCA adapters model (parking)
- Status: TODO
- Scope:
  - api/models/sca_adapters.py
- Origin: new untracked in banxe-emi-stack working tree
- Goal: formalize SCA adapters model under auth scope (align with
  IL-SCA2F-* / services/auth/sca_service_port.py).

---

### IL-COMPSYNC-0X — parking map v3 recorded (reference)
- Status: TODO
- Scope snapshot: /tmp/banxe_parking_il_contours_v3_20260422192527.txt
- Notes:
  - Parking map v3 enumerates IL-COMPSYNC-0X / IL-FRAUDTRACE-0X /
    IL-MIDAZMCP-0X with full file-level scope from working tree snapshot.
  - No code or tests are promoted to tracked state by this record.

### IL-COMPSYNC-MCP-TOOLS-FIX — TODO (new blocker)
- Status: TODO
- Scope:
  - banxe_mcp/server.py (missing name: compliance_scan)
  - tests/test_compliance_sync/test_mcp_tools.py
- Observed failure under pytest-fast:
  - ImportError: cannot import name 'compliance_scan' from 'banxe_mcp.server'
  - Test: TestComplianceMCPTools::test_compliance_scan_returns_json
- Owner scope: IL-COMPSYNC-0X family (compliance_sync MCP tools)
- Blocks: IL-LINT-03 commit proof (adds to IL-CNS-AUD-PIPELINE-FIX and
  IL-OBS-MCP-TESTS-FIX)

---

### IL-LINT-03 — DONE (anchored, mixed-scope deviation)
- Status: DONE
- Proof SHA: 7708d4c541df94083bcd379d8aa005740617ec57
- Proof SHA subject: "feat(sprint-39): Phase 54 Compliance Sync + Midaz MCP + Fraud Tracer [IL-CMS-01 + IL-MCP-01 + IL-TRC-01]"
- Deviation: IL-LINT-03 scoped diff (defusedxml + FrozenInstanceError + I001 across
  services/batch_payments/file_parser.py, tests/test_card_issuing/test_models.py,
  tests/test_multi_currency/test_models.py) landed inside sprint-39 mixed commit
  instead of a dedicated fix(lint) commit.
- Mitigation: this ledger-only entry retroactively anchors IL-LINT-03 proof to the
  existing commit; no code or tests are touched by this entry.
- Recovery check: HEAD sha256 == WKTREE sha256 for all three scoped files;
  HEAD parser contains "defusedxml.ElementTree", "DefusedET.fromstring",
  "DefusedET.ParseError".

### IL-CNS-AUD-PIPELINE-FIX — DONE
- Status: DONE
- Proof: pytest-fast Passed on tests/test_integration/test_consent_audit_pipeline.py in EMI pre-commit run 2026-04-22T17:50:21Z

### IL-OBS-MCP-TESTS-FIX — DONE
- Status: DONE
- Proof: pytest-fast Passed on tests/test_observability/test_mcp_tools_observability.py in EMI pre-commit run 2026-04-22T17:50:21Z

### IL-COMPSYNC-MCP-TOOLS-FIX — DONE
- Status: DONE
- Proof: banxe_mcp/server.py exposes compliance_scan + compliance_gaps; pytest-fast Passed in EMI pre-commit run 2026-04-22T17:50:21Z


---

### IL-COMPSYNC-0X — resolve v1
- Status: DONE
- Proof/notes: tracked in HEAD (9 files), last path SHA=82b69b2d21a61328eae1b925566ec6860c0e13fd


### IL-FRAUDTRACE-0X — resolve v1
- Status: DONE
- Proof/notes: tracked in HEAD (9 files), last path SHA=82b69b2d21a61328eae1b925566ec6860c0e13fd


### IL-MIDAZMCP-0X — resolve v1
- Status: DONE
- Proof/notes: tracked in HEAD (9 files), last path SHA=82b69b2d21a61328eae1b925566ec6860c0e13fd


### IL-SCA-ADAPTERS-0X — resolve v1
- Status: DONE
- Proof/notes: tracked in HEAD (1 files), last path SHA=82b69b2d21a61328eae1b925566ec6860c0e13fd


---

### IL-LINT-03 — anchor correction (supersedes prior anchor)
- parent-cycle: housekeeping/lint-hygiene
- amendment-ref: (n/a — code hygiene, no constitutional amendment)
- source: anchor probe /tmp/il_lint_03_real_anchor_*.log
- status: integrated
- status-history:
  - proposed @ 2026-04-22 (initial IL-LINT-03 OPEN ticket, ledger commit 3fcb668)
  - accepted @ 2026-04-22 (scoped fix verified green: ruff/bandit/py_compile/pytest)
  - integrated @ 2026-04-22 (true code anchor identified: ba3fccc)
- scope:
  - banxe-emi-stack: services/batch_payments/file_parser.py
  - banxe-emi-stack: tests/test_card_issuing/test_models.py
  - banxe-emi-stack: tests/test_multi_currency/test_models.py
- integration-rule: anchor-only correction; no code or test files touched here.
- anchors:
  - CODE PROOF: ba3fccc (full ba3fccceaa376b6ec1273f416bd6fb916353fca6) "feat(sprint-38): Phase 53 Integration Hardening + Observability [IL-INT-01 + IL-OBS-01]"
- verification:
  - probe markers: defusedxml.ElementTree as DefusedET in parser; pytest.raises(FrozenInstanceError) in both test_models.py
  - emi-stack proof commit: ba3fccceaa376b6ec1273f416bd6fb916353fca6
  - sha256-anchors:
      services/batch_payments/file_parser.py: b04d2d5af95cb5fa61f8a57b48b252e0db2a3d23db6d75fdf278c2950ee96cc6
      tests/test_card_issuing/test_models.py:   0351fb3b4395fcf8923703819b68610c7025eb4090c80e982479b4a363227eee
      tests/test_multi_currency/test_models.py:     599beb64531c0f074baa06a080c6b786ce64acac4fd30f88c2e35a0ea49b5f64
- deviations:
  - prior-anchor-mistake: earlier ledger commit 693ecab
    (docs(ledger): IL-LINT-03 DONE anchored to 7708d4c) recorded a
    wrong proof SHA. 7708d4c is sprint-39 Phase 54 and does NOT
    modify any of the three scoped files; it merely inherits them from
    ba3fccc. The earlier entry stays in ledger history as record
    but is now superseded.
- supersedes: prior IL-LINT-03 entry with anchor 7708d4c (ledger commit 693ecab63359b50a2c839b858f8e25b9706f4d6d)
- privileged-ops:
  - git tag: NOT EXECUTED
  - gh release: NOT EXECUTED
- successor: (none)
- notes:
  Real chronological history of the three scoped files contains 4 commits;
  this is the first one where all three IL-LINT-03 markers are present, hence
  the canonical proof SHA. Anchor-only correction; no code or tests touched.


---

### IL-LINT-03 — anchor correction
- Status: integrated
- Real proof SHA: ba3fccceaa376b6ec1273f416bd6fb916353fca6
- Supersedes: prior anchor 7708d4c (ledger commit 693ecab)
- Reason: 7708d4c does not modify the three IL-LINT-03 files; ba3fccc does.


---

### IL-LINT-03 — anchor correction
- Status: integrated
- Real proof SHA: ba3fccceaa376b6ec1273f416bd6fb916353fca6
- Supersedes: prior anchor 7708d4c (ledger commit 693ecab)
- Reason: 7708d4c does not modify the three IL-LINT-03 files; ba3fccc does.


---

### IL-LINT-03 — anchor correction
- Status: integrated
- Real proof SHA: ba3fccceaa376b6ec1273f416bd6fb916353fca6
- Supersedes: prior anchor 7708d4c (ledger commit 693ecab)
- Reason: 7708d4c does not modify the three IL-LINT-03 files; ba3fccc does.


---

### IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12
- Date: 2026-05-12
- Status: DONE (prep package only; no production deploy)
- Scope: Sub-B autonomous prep for G-IAM-08 mitigation (Keycloak DB
  password exposed in keycloak.service ExecStart on evo1). This entry
  documents repo-only scaffolding; production mitigation on evo1 remains
  gated by Central + operator approval per HITL gate in the migration plan.
- Files created (under `infra/keycloak/`):
  - `G-IAM-08-MIGRATION-PLAN.md`
  - `keycloak.service.d/g-iam-08-fix.conf.template`
  - `db.password.template`
  - `install-db-password-file.sh` (executable)
  - `validate-g-iam-08-mitigation.sh` (executable; 17/17 PASS local run)
  - `OPERATOR-RUNBOOK-G-IAM-08.md`
- Recommended mitigation: native KC 26.x `--db-password-file=/etc/keycloak/db.password`
  (file root:keycloak 0640); systemd drop-in replaces `ExecStart`. Rejected
  alternative: `EnvironmentFile=` (leaks via `/proc/<pid>/environ`).
- Anchors: G-IAM-08, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
  IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 (Sprint S12.5),
  IL-CANON-TERMINAL-B-AUTONOMOUS-FIXATION-2026-05-12,
  IL-CANON-EXPLICIT-TARGET-INSTRUCTION-2026-05-12.
- Production mitigation remains gated by Central + operator approval; no
  evo1 deploy, no `systemctl daemon-reload`, no ssh evo1 performed by this PR.


---

### IL-OPS-S12-6-G-IAM-09-PREP-2026-05-12
- Date: 2026-05-12
- Status: DONE (prep package only; no production deploy)
- Scope: Sub-B autonomous prep for G-IAM-09 mitigation (no Keycloak
  backups present on evo1 — zero RPO, violates ADR-029 + FCA SYSC 4.1.5).
  This entry documents repo-only scaffolding; production deploy of the
  backup policy + first restore drill remain gated by Central + operator
  approval per HITL gate in `G-IAM-09-BACKUP-POLICY.md` §6.
- Files created (under `infra/keycloak/`):
  - `G-IAM-09-BACKUP-POLICY.md` (policy + ADR-029 alignment matrix + deploy + rollback + HITL)
  - `OPERATOR-RUNBOOK-G-IAM-09-RESTORE-DRILL.md` (sandbox-only drill flow + sign-off)
  - `scripts/kc-backup.sh.template` (pg_dump -Fc → gpg AES256 → sha256 → off-host)
  - `scripts/validate-g-iam-09-backup-prep.sh` (offline lint; 29/29 PASS local run)
  - `cron.d/kc-backup.cron.template` (daily 02:30; placeholders for wrapper + log path)
  - `examples/backup.env.example` (env placeholders; no secrets)
  - `examples/offhost-target.example` (off-host transport variants)
- Credential flow: backup wrapper reuses the `/etc/keycloak/db.password`
  file landed by IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12 (PR #133, merged
  f37f866) — no plaintext password in CLI args, env, cron, or any template.
- ADR-029 alignment: format + retention + drill cadence proposed defaults;
  values not specified in canonical ADR-029 carry explicit TODO markers in
  the alignment matrix. Bank-side `services/backup/` code (BackupPort,
  PgDumpBackupAdapter, RestoreDrillPort, OffsiteUploadPort) referenced
  as concrete implementation anchors.
- Anchors: G-IAM-09, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
  IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 (Sprint S12.6),
  IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12 (credential-file sibling),
  IL-CANON-TERMINAL-B-AUTONOMOUS-FIXATION-2026-05-12,
  IL-CANON-EXPLICIT-TARGET-INSTRUCTION-2026-05-12.
- Production deploy + first restore drill remain gated by Central +
  operator approval; no evo1 deploy, no `pg_dump` execution against
  production, no `systemctl daemon-reload`, no `ssh evo1` performed.


---

### IL-S16-4-SAFEGUARDING-RECONCILIATION-PREP-2026-05-12
- Date: 2026-05-12
- Status: DONE (prep package only; no production deploy)
- Scope: Sub-B autonomous prep for the Safeguarding + Reconciliation
  engine (Sprint S16.4 / Block J + D-recon). Domain model + ports +
  Modulr stub + algorithm sketch + offline validator + operator runbook.
  Production deploy of the engine and the first LIVE run remain gated by
  Central + operator + MLRO sign-off per HITL gate in the runbook.
- Files created:
  - `services/safeguarding/internal/reconciliation/domain.py` (D1)
  - `services/safeguarding/internal/adapters/modulr_safeguarding_stub.py` (D2)
  - `services/safeguarding/internal/reconciliation/algorithm.md` (D3)
  - `services/safeguarding/scripts/validate-prep.sh` (D4, executable; 33/33 PASS)
  - `docs/runbooks/safeguarding-reconciliation-deploy-2026-05-12.md` (D5)
- Recon scope per FCA CASS 15 §15.10 + ADR-013/014/015: daily
  reconciliation of e-money outstanding vs Modulr safeguarding-account
  balance; threshold-based break detection (absolute minor-units +
  relative basis-points + currency); ClickHouse Guardian audit per
  ADR-027; MLRO notification on EMERGENCY threshold via Sprint S20.5
  Telegram channel; idempotent on `run_id`.
- Anchors: Sprint S16.4 (IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11),
  ADR-013 (Midaz CBS primary), ADR-014 (composable financial stack),
  ADR-015 (payment processing stack), ADR-027 (audit-trail durability),
  FCA SUP 15, FCA CASS 15 §15.10,
  IL-CANON-TERMINAL-B-AUTONOMOUS-FIXATION-2026-05-12,
  IL-CANON-EXPLICIT-TARGET-INSTRUCTION-2026-05-12,
  IL-CANON-SUB-B-PROMPT-VIA-FILE-2026-05-12.
- Production deploy + first LIVE run remain gated by Central + operator +
  MLRO sign-off; no evo1 deploy, no live Modulr API calls, no live DB
  writes, no `ssh evo1`, no `systemctl daemon-reload` performed.

### IL-CBS-DGL-FAILCLOSED-2026-06-26
- Date: 2026-06-26
- Status: DONE (offline; no live infra)
- Scope: D-gl GL-core fail-closed fix — first cross-repo runtime increment
  promoting the `banxe-architecture` D-GL-BUILD-SPEC (IL-484) DoD #8
  (`test_midaz_unavailable_surfaces_infra_failure`). The Midaz ledger adapter
  previously swallowed transport/HTTP failures and returned a SILENT
  `Decimal("0")` / `None` / `[]` — a false zero balance that can drive a wrong
  reconciliation tie-out or safeguarding figure. Now an unreachable backend /
  transport-timeout / 5xx raises `LedgerInfrastructureError` (the failure
  SURFACES); a reachable, definite answer (4xx, or HTTP-200 with no GBP item)
  keeps the safe default. The reconciliation engine (confirmed direct consumer)
  maps the surfaced error per-account to a fail-closed `ERROR` result — never a
  false `MATCHED`/`DISCREPANCY`.
- Files modified:
  - `services/ledger/ledger_port.py` (new `LedgerInfrastructureError`)
  - `services/ledger/midaz_adapter.py` (3 methods fail-closed: get_balance /
    create_transaction / list_transactions)
  - `services/recon/reconciliation_engine.py` (per-account fail-closed `ERROR`)
  - `tests/test_ledger_adapter.py` (3 silent-fallback assertions → `raises`)
- Files created:
  - `tests/test_midaz_fail_closed.py`
  - `tests/test_recon_failclosed.py`
- Out of scope (deferred): transaction lifecycle (commit/cancel/revert),
  Fineract fallback adapter + ledger factory, high-value approval persistence,
  and the `api/routers/ledger.py` 503 mapping (separate `midaz_client` path,
  `# pragma: no cover` — follow-up). Protocol method set unchanged; only the
  exception is added → no adapter-wide ripple.
- Verification: 238 tests pass offline (44 fail-closed/updated + 194
  back-compat: gl_service / payment_posting / reconciliation / api_ledger /
  api_recon); ruff + ruff-format clean; semgrep banxe-rules clean; Decimal-only
  (I-01); no secrets; no live Midaz/ClickHouse calls.
- Landing discipline: cross-repo runtime authorized by operator; D-gl chosen as
  first block; narrow first increment per operator directive. No live infra
  activation. No self-merge — PR opened for operator review/merge.
- Anchors: `banxe-architecture` D-GL-BUILD-SPEC (IL-484) §5 DoD #8; ADR-013
  (Midaz CBS primary); FCA CASS 7.15 daily reconciliation; I-01 (Decimal),
  I-24 (audit append-only), I-28 (LedgerPort-only).

### IL-CBS-DGL-LIFECYCLE-2026-06-26
- Date: 2026-06-26
- Status: DONE (offline; no live infra)
- Scope: D-gl GL-core transaction lifecycle (second cross-repo runtime
  increment promoting D-GL-BUILD-SPEC IL-484 DoD #4 `test_transaction_lifecycle`).
  Mirrors the Midaz transaction lifecycle, additive over the legacy immediate
  `post_journal_entry`: stage `create_journal_entry` (PENDING) → `commit`
  (COMMITTED, counts) | `cancel` (CANCELLED, no balance); `revert` a
  POSTED/COMMITTED entry (original → REVERSED, dropped from balance, plus a
  lineage reversing entry — single mechanism, no double-count); `annotate`
  (records-only NOTED, never a balance impact). Balance now derives from
  POSTED + COMMITTED (`BALANCE_AFFECTING_STATUSES`); legacy POSTED still counts.
- Files modified:
  - `services/ledger/ledger_models.py` (PostingStatus += COMMITTED/CANCELLED/
    NOTED; `BALANCE_AFFECTING_STATUSES`)
  - `services/ledger/ledger_port.py` (5 lifecycle methods on the Protocol)
  - `services/ledger/inmemory_ledger.py` (lifecycle impl + balance derivation)
  - `services/ledger/gl_service.py` (commit/cancel/revert/annotate wrappers,
    each records a GLAuditEntry — I-24)
- Files created:
  - `tests/test_ledger_lifecycle.py` (14 tests: create→commit, cancel,
    revert-nets-to-zero, annotate-no-balance, legacy back-compat, audit rows)
- Out of scope (deferred): Fineract fallback + ledger factory; api-router 503
  mapping; high-value approval audit persistence.
- Verification: 226 ledger/recon tests pass offline (incl. back-compat
  gl_service / payment_posting / ledger_adapter / reconciliation / api_ledger);
  ruff + format clean; semgrep banxe-rules clean; Decimal-only (I-01); no live
  Midaz/ClickHouse. LedgerPort Protocol additive; only InMemoryLedger implements
  it (Midaz/Stub adapters are recon-shaped, unaffected).
- Landing: sandbox-autonomous mode — green PR auto-merged when CLEAN.
- Anchors: D-GL-BUILD-SPEC (IL-484) §3.3/§5 DoD #4; ADR-013; I-01, I-24, I-28.

### IL-CBS-DGL-API503-2026-06-26
- Date: 2026-06-26
- Status: DONE (offline; no live infra)
- Scope: D-gl API fail-closed mapping (third cross-repo runtime increment),
  completing DoD #8 at the API edge. The ledger API production branch
  previously surfaced raw httpx errors (and `midaz_client` swallowed nothing
  explicitly); now `midaz_client.get_balance`/`list_accounts` fail closed
  (transport/5xx → `LedgerInfrastructureError`; 4xx / no-GBP → safe default),
  and `api/routers/ledger.py` maps `LedgerInfrastructureError` → **HTTP 503**
  (Ledger temporarily unavailable), keeping reachable "not found" → **404**.
  The previously `# pragma: no cover` production paths are now covered.
- Files modified:
  - `services/ledger/midaz_client.py` (fail-closed get_balance/list_accounts;
    removed a dead un-awaited client.get line in the rewritten get_balance body)
  - `api/routers/ledger.py` (LedgerInfrastructureError → 503; None → 404)
- Files created:
  - `tests/test_api_ledger_failclosed.py` (503 on infra error, 404 on None,
    200 happy, for both balance + list endpoints; fake midaz_client injected,
    `_is_sandbox` forced False — offline)
- Out of scope (deferred): Fineract fallback (operator-gated, no API ref — see
  C steer); high-value approval audit (next increment).
- Verification: API + ledger suites pass offline (incl. existing sandbox API
  tests); ruff + format clean; semgrep banxe-rules clean; Decimal-only (I-01).
- Landing: sandbox-autonomous mode — green PR auto-merged when CLEAN.
- Anchors: D-GL-BUILD-SPEC (IL-484) §5 DoD #8 (API edge); ADR-013; FCA CASS
  7.15; I-01, I-28.

### IL-CBS-DGL-APPROVAL-2026-06-26
- Date: 2026-06-26
- Status: DONE (offline; no live infra)
- Scope: D-gl high-value approval audit (fourth cross-repo runtime increment,
  D-GL-BUILD-SPEC IL-484 DoD #5 `test_high_value_posting_requires_approval`).
  A posting ≥ HIGH_VALUE_THRESHOLD (£50k) is staged (never auto-posted, I-04)
  and recorded PENDING in an append-only approval store (I-24). A NAMED human
  must `approve_high_value` (posts the entry) or `reject_high_value` (does not);
  both raise on a blank approver (I-27 — AI proposes, never auto-approves). The
  bool `high_value_approved` fast-path is unchanged (back-compat).
- Files created:
  - `services/ledger/approval_models.py` (ApprovalDecision, HighValueApproval
    Decimal model, ApprovalStorePort, append-only InMemoryApprovalStore)
  - `tests/test_high_value_approval.py` (8 tests: PENDING recorded, approve
    requires human + posts, reject requires human + no post, append-only store,
    below-threshold direct post, unknown raises)
- Files modified:
  - `services/ledger/gl_service.py` (stage high-value entry + record PENDING;
    `approve_high_value` / `reject_high_value` with named-approver guard + audit;
    builds the JournalEntry before the high-value branch)
- Out of scope (deferred / operator-gated): Fineract fallback (no API ref).
  This completes the in-codebase D-gl runtime increments; next per critical
  path = E-safeguard / D-recon runtime (recon_port + D-gl Leg A now landed).
- Verification: 146 ledger/api tests pass offline (incl. back-compat
  gl_service / payment_posting / lifecycle / adapter / api); ruff + format
  clean; semgrep banxe-rules clean; Decimal-only (I-01).
- Landing: sandbox-autonomous mode — green PR auto-merged when CLEAN.
- Anchors: D-GL-BUILD-SPEC (IL-484) §5 DoD #5; ADR-013; I-01, I-04, I-24, I-27.

### IL-CBS-DRECON-3LEG-2026-06-26
- Date: 2026-06-26
- Status: DONE (offline; no live infra)
- Scope: D-recon / E-safeguard runtime — first increment: CASS 15 three-leg
  tie-out (D-RECON-BUILD-SPEC IL-474 §3). A (Midaz ledger) == B (safeguarding
  account) == C (payment rail) within the penny-exact tolerance (£0.01),
  reusing the shared `src/recon_core` mechanics (`evaluate_balances` +
  `BreachEvaluator("BREAK")`). Adds the missing **Leg C** source
  (`RailBalancePort` + `InMemoryRailBalancePort`) and the `three_leg_reconcile`
  tie-out with signed-difference SHORTFALL detection (client-fund ledger > 
  safeguarding account ⇒ under-safeguarded → escalate MLRO/CFO, CASS 15).
- ADR-102 CANONICAL DECISION (live-audit, origin/main ebfeac6): the safeguarding
  recon stack is consolidated onto **`src/recon_core/`** (shared mechanics, #164)
  with a regime split — **CASS 15 = `src/safeguarding/`** (£0.01 BREAK), CASS 7.15
  = `services/recon/reconciliation_engine_v2` (£100 HITL). Legacy/dormant
  `reconciliation_engine.py` (old cron) + `recon_engine.py` (tests-only) are NOT
  extended. This increment targets the CASS 15 (`src/safeguarding/`) path only.
- BEST-DECISION REORDER (stated): the operator's recommended first increment
  "SafeguardingAccountPort (Leg B)" ALREADY EXISTS as `BankStatementPort` in
  `src/safeguarding/agent.py` (Leg A = `LedgerBalancePort`, Leg B =
  `BankStatementPort`, A-vs-B recon + breach + audit already implemented).
  Building it would duplicate (ADR-102). The genuine foundational gap is the
  THIRD leg + the A==B==C tie-out — delivered here.
- Files created:
  - `src/safeguarding/three_leg.py` (RailBalancePort/InMemoryRailBalancePort,
    ThreeLegStatus, ThreeLegResult, three_leg_reconcile)
  - `tests/test_safeguarding_three_leg.py` (11 tests: MATCHED/BREAK/PENDING,
    penny tolerance, shortfall vs surplus, signed diff, rail port)
- Out of scope (next increments): wire 3-leg into SafeguardingAgent.run();
  BreachNotifyPort + MLRO/CFO HITL escalation port; unified `safeguarding_events`
  audit-table consolidation.
- Verification: 11 new + 95 back-compat (src_safeguarding, src_safeguarding_agent,
  recon_core) pass offline; ruff + format clean; semgrep banxe-rules clean;
  Decimal-only (I-01). Additive — 2-leg `daily_reconciliation.py` / orchestrator
  untouched.
- Landing: sandbox-autonomous mode — green PR auto-merged when CLEAN.
- Anchors: D-RECON-BUILD-SPEC (IL-474) §3 (3-leg); ADR-SAF-01; recon_core S6.2
  boundary (#164); I-01, I-24.

### IL-CBS-LEDGER-ERRATA-DRECON3LEG-2026-06-26
- Date: 2026-06-26
- Status: DONE (append-only errata; no code change)
- Scope: Forward-fix for IL key collision — `IL-CBS-DRECON-3LEG-2026-06-26` was
  assigned to two distinct PRs in the same factory cycle.
- Collision:
  - Commit `0c5c78d` / PR #218: `feat(safeguarding): CASS 15 three-leg tie-out
    (A==B==C) + Leg C rail port` — engine implementation
    (`src/safeguarding/three_leg.py`, 11 tests).
  - Commit `9ba9c8a` / PR #219 (branch `agent/factory/safeguarding/wire-3leg-agent`):
    `feat(safeguarding): wire three_leg_reconcile into SafeguardingAgent` — agent
    wiring (`src/safeguarding/agent.py`). This PR reused the parent IL key instead
    of minting a unique derivative.
- Canonical assignment (forward, history unchanged):
  - PR #218 keeps: `IL-CBS-DRECON-3LEG-2026-06-26` (engine — the original owner).
  - PR #219 is re-designated: `IL-CBS-DRECON-3LEG-WIRE-2026-06-26` (errata; commit
    cannot be edited — append-only correction per ADR-059-A).
- Root cause: factory reused the parent build-spec IL key on the dependent wiring
  PR without incrementing. Single factory cycle produced two PRs against the same
  spec anchor without a sub-key differentiation step.
- Prevention (added to per-cycle checklist): each PR MUST carry a UNIQUE IL key.
  Before submitting a dependent PR that derives from a parent spec, append a
  distinguishing suffix (e.g., `-WIRE`, `-API`, `-TESTS`, `-AGENT`) so the key
  is globally unique across the git log. Verify with:
  `git log --oneline | grep -oP 'IL-[A-Z0-9-]+' | sort | uniq -d` — must be empty.
- Invariants: ADR-059-A (append-only; no history rewrite); no force-push; no
  renumbering of existing commits.
- Verification: `git log --oneline | grep -oP 'IL-[A-Z0-9-]+' | sort | uniq -d`
  returns empty after this errata lands (the collision exists only in the pre-errata
  history; this entry documents and closes it).
- This errata PR own key: `IL-CBS-LEDGER-ERRATA-DRECON3LEG-2026-06-26` (unique).

### IL-CBS-CI-QUALITYGATE-2026-06-26

**Task:** O-11 — wire quality-gate advisory step into banxe-emi-stack CI
**Status:** OPEN (pending operator review / promote-to-required)
**Scope:** `.github/workflows/quality-gate.yml` (advisory job `quality-gate-advisory`, continue-on-error: true)
**KPIs:**
  - KPI-1: coverage ≥85% (pytest --cov-fail-under=85, advisory, non-blocking)
  - KPI-2: tech-debt ⚪ DELEGATED (SonarQube not yet configured; ruff statistics as proxy only)
  - KPI-4: security hotspot ≥95% (semgrep 0 findings, advisory, non-blocking)
**Design:** All sub-steps `continue-on-error: true` — green main preserved; non-blocking. Advisory job depends on [test, semgrep] baseline gates (required). Comment in YAML: "promote-to-required is operator-gate".
**Invariants:** I-27 (HITL), ADR-102 (no duplication — extends existing quality-gate.yml rather than creating new), I-28 (audit trail via IL), I-24 (append-only).
**Operator gates pending:**
  - [ ] Promote advisory → required (separate operator decision, not autonomous)
  - [ ] KPI-2 tech-debt: configure SonarQube or equivalent when ready
  - [ ] Coverage baseline: confirm 85% threshold is achievable against current test suite
**Proof:**
  - YAML parses: ✅
  - ADR-102: extends existing quality-gate.yml (lines 209–253), no new workflow file ✅
  - IL key unique: `grep 'IL-CBS-CI-QUALITYGATE-2026-06-26' INSTRUCTION-LEDGER.md | wc -l` = 1 ✅
