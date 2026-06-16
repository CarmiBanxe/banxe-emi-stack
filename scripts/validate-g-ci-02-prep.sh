#!/usr/bin/env bash
# validate-g-ci-02-prep.sh — offline validator for the S16.5 G-CI-02 prep
# package. NO network mutation. NO call to GitHub. Pure-local lint of:
#   - .github/protection-update-v2.json (well-formed + schema invariants)
#   - cross-reference: every context exists in .github/workflows/*.yml OR
#     is on the known-external allowlist (guardian-* GitHub App checks)
#
# Anchors:
#   S16.5; ADR-035 G-CI-02 prep; ADR-035 Step 3 baseline.
#
# Exit codes:
#   0  all checks PASS
#   1  at least one check FAIL

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROTECTION_JSON="${ROOT_DIR}/.github/protection-update-v2.json"
WORKFLOWS_DIR="${ROOT_DIR}/.github/workflows"
RUNBOOK="${ROOT_DIR}/docs/runbooks/branch-protection-g-ci-02-deploy-2026-05-12.md"

# Externally-provided checks (GitHub App, not in our YAML).
KNOWN_EXTERNAL=(
  "guardian-factory"
  "guardian-project"
)

pass=0
fail=0

ok()    { echo "  [PASS] $*"; pass=$((pass + 1)); }
bad()   { echo "  [FAIL] $*"; fail=$((fail + 1)); }
check() { local label=$1; shift; if "$@"; then ok "$label"; else bad "$label"; fi }

exists() { [[ -f "$1" ]]; }
json_valid() { jq empty "$1" >/dev/null 2>&1; }
json_eq() { local file=$1 path=$2 want=$3; [[ "$(jq -r "$path" "$file")" == "$want" ]]; }
json_jq_truthy() { local file=$1 expr=$2; [[ "$(jq -r "$expr" "$file")" == "true" ]]; }
json_jq_count_ge() { local file=$1 expr=$2 min=$3; [[ "$(jq -r "$expr" "$file")" -ge "$min" ]]; }
contains_check_context() {
    local file=$1 want=$2
    jq -e --arg w "$want" '.required_status_checks.checks[].context | select(. == $w)' "$file" >/dev/null 2>&1
}
is_in_external_allowlist() {
    local want=$1
    for e in "${KNOWN_EXTERNAL[@]}"; do
        [[ "$e" == "$want" ]] && return 0
    done
    return 1
}
context_in_some_workflow() {
    local want=$1
    grep -RF "name: $want" "${WORKFLOWS_DIR}" >/dev/null 2>&1
}

echo "S16.5 G-CI-02 prep offline validation"
echo "----------------------------------------"

echo "[1] File presence"
check "protection-update-v2.json present"  exists "$PROTECTION_JSON"
check "runbook present"                    exists "$RUNBOOK"

echo "[2] JSON well-formedness"
check "protection-update-v2.json parses as JSON"  json_valid "$PROTECTION_JSON"

echo "[3] Schema invariants"
check "strict == true" \
    json_eq "$PROTECTION_JSON" '.required_status_checks.strict' "true"
check "enforce_admins == false" \
    json_eq "$PROTECTION_JSON" '.enforce_admins' "false"
check "required_pull_request_reviews preserved as null" \
    json_eq "$PROTECTION_JSON" '.required_pull_request_reviews' "null"
check "restrictions preserved as null" \
    json_eq "$PROTECTION_JSON" '.restrictions' "null"
check "checks array length >= 9 (3 baseline + at least 6 new gates)" \
    json_jq_count_ge "$PROTECTION_JSON" '.required_status_checks.checks | length' 9

echo "[4] Baseline preservation (ADR-035 Step 3)"
check "Smoke Gate (mock tier) preserved" \
    contains_check_context "$PROTECTION_JSON" "Smoke Gate (mock tier)"
check "guardian-factory preserved (external)" \
    contains_check_context "$PROTECTION_JSON" "guardian-factory"
check "guardian-project preserved (external)" \
    contains_check_context "$PROTECTION_JSON" "guardian-project"

echo "[5] G-CI-02 newly-required gates present"
check "Smoke Gate (real stack) listed" \
    contains_check_context "$PROTECTION_JSON" "Smoke Gate (real stack)"
check "Pytest (coverage >= 80%) listed" \
    contains_check_context "$PROTECTION_JSON" "Pytest (coverage >= 80%)"
check "Ruff lint + format listed" \
    contains_check_context "$PROTECTION_JSON" "Ruff lint + format"
check "Semgrep (banxe-rules) listed" \
    contains_check_context "$PROTECTION_JSON" "Semgrep (banxe-rules)"
check "Gitleaks - Secrets Scan listed" \
    contains_check_context "$PROTECTION_JSON" "Gitleaks - Secrets Scan"
check "Biome lint + format (Frontend) listed" \
    contains_check_context "$PROTECTION_JSON" "Biome lint + format (Frontend)"
check "Vitest (frontend) listed" \
    contains_check_context "$PROTECTION_JSON" "Vitest (frontend)"
check "Alembic — schema drift check listed" \
    contains_check_context "$PROTECTION_JSON" "Alembic — schema drift check"

echo "[6] Cross-reference: each context exists in workflows or external allowlist"
fail_xref=0
while IFS= read -r ctx; do
    if context_in_some_workflow "$ctx"; then
        ok "context resolved in workflows: ${ctx}"
    elif is_in_external_allowlist "$ctx"; then
        ok "context on known-external allowlist: ${ctx}"
    else
        bad "context not found in workflows or external allowlist: ${ctx}"
        fail_xref=$((fail_xref + 1))
    fi
done < <(jq -r '.required_status_checks.checks[].context' "$PROTECTION_JSON")

echo "[7] Schema-guard: no unexpected top-level keys"
unexpected="$(jq -r '
    [keys[]
     | select(. != "_comment_anchors"
              and . != "required_status_checks"
              and . != "enforce_admins"
              and . != "required_pull_request_reviews"
              and . != "restrictions")]
    | join(",")
' "$PROTECTION_JSON")"
check "no unexpected top-level keys (got: '${unexpected:-none}')" \
    test -z "$unexpected"

echo "----------------------------------------"
echo "Summary: ${pass} PASS / ${fail} FAIL"

if [[ "$fail" -gt 0 ]]; then
    exit 1
fi
