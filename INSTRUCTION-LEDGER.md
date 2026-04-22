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
