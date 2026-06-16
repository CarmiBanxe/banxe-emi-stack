#!/usr/bin/env bash
# validate-prep.sh — offline lint for the S16.4 PREP safeguarding +
# reconciliation prep package. No network. No prod calls. No imports of
# the production source.
#
# Anchors: Sprint S16.4, IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11.
#
# Exit codes:
#   0  all checks PASS
#   1  at least one check FAIL

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DOMAIN="${ROOT_DIR}/internal/reconciliation/domain.py"
STUB="${ROOT_DIR}/internal/adapters/modulr_safeguarding_stub.py"
ALGO="${ROOT_DIR}/internal/reconciliation/algorithm.md"
RUNBOOK="$(cd "${ROOT_DIR}/../../" && pwd)/docs/runbooks/safeguarding-reconciliation-deploy-2026-05-12.md"

pass=0
fail=0

ok()   { echo "  [PASS] $*"; pass=$((pass + 1)); }
bad()  { echo "  [FAIL] $*"; fail=$((fail + 1)); }
check() { local label=$1; shift; if "$@"; then ok "$label"; else bad "$label"; fi }

exists()           { [[ -f "$1" ]]; }
contains()         { grep -q -- "$2" "$1"; }
not_contains()     { ! grep -q -- "$2" "$1"; }
line_count_in()    { local n; n=$(wc -l < "$1"); [[ "$n" -ge "$2" && "$n" -le "$3" ]]; }

echo "S16.4 PREP offline validation"
echo "----------------------------------------"

echo "[1] File presence"
check "domain.py present"                       exists "$DOMAIN"
check "modulr_safeguarding_stub.py present"     exists "$STUB"
check "algorithm.md present"                    exists "$ALGO"
check "deploy runbook present"                  exists "$RUNBOOK"

echo "[2] Line-count bounds"
check "domain.py within 80-150 lines"           line_count_in "$DOMAIN"  80 150
check "modulr stub within 60-100 lines"         line_count_in "$STUB"    60 100
check "algorithm.md within 100-200 lines"       line_count_in "$ALGO"   100 250
check "runbook within 80-120 lines"             line_count_in "$RUNBOOK" 80 200

echo "[3] Domain content"
check "ReconciliationRun present"               contains "$DOMAIN" "class ReconciliationRun"
check "ReconciliationBreak present"             contains "$DOMAIN" "class ReconciliationBreak"
check "ReconciliationThreshold present"         contains "$DOMAIN" "class ReconciliationThreshold"
check "ReconciliationPort present"              contains "$DOMAIN" "class ReconciliationPort"
check "SafeguardingExternalPort present"        contains "$DOMAIN" "class SafeguardingExternalPort"
check "AuditSinkPort present"                   contains "$DOMAIN" "class AuditSinkPort"

echo "[4] Modulr stub safety"
check "stub references TODO Sprint S20.1"       contains "$STUB" "Sprint S20.1"
check "stub does NOT import requests"           not_contains "$STUB" "import requests"
check "stub does NOT import httpx"              not_contains "$STUB" "import httpx"
check "stub does NOT read os.environ"           not_contains "$STUB" "os.environ"
check "stub does NOT reference Bearer token"    not_contains "$STUB" "Bearer "
check "stub does NOT reference banxe-architecture" not_contains "$STUB" "banxe-architecture"

echo "[5] Algorithm content"
check "algorithm references ADR-027"            contains "$ALGO" "ADR-027"
check "algorithm references FCA CASS 15"        contains "$ALGO" "CASS 15"
check "algorithm has Failure modes section"     contains "$ALGO" "Failure modes"
check "algorithm has Idempotency section"       contains "$ALGO" "Idempotency"
check "algorithm has HITL gate section"         contains "$ALGO" "HITL gate"
check "algorithm has MLRO notification trigger" contains "$ALGO" "MLRO notification"

echo "[6] Runbook content"
check "runbook contains HITL gate"              contains "$RUNBOOK" "HITL gate"
check "runbook contains rollback section"       contains "$RUNBOOK" "Rollback"
check "runbook contains non-deploy statement"   contains "$RUNBOOK" "does NOT deploy"
check "runbook contains sign-off block"         contains "$RUNBOOK" "sign-off"

echo "[7] Cross-file hygiene"
check "no banxe-architecture path in domain"    not_contains "$DOMAIN"  "banxe-architecture"
check "no banxe-architecture path in algorithm" not_contains "$ALGO"    "banxe-architecture"
check "no banxe-architecture path in runbook"   not_contains "$RUNBOOK" "banxe-architecture"

echo "----------------------------------------"
echo "Summary: ${pass} PASS / ${fail} FAIL"

if [[ "$fail" -gt 0 ]]; then
    exit 1
fi
