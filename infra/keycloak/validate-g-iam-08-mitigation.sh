#!/usr/bin/env bash
# validate-g-iam-08-mitigation.sh — offline validator for the G-IAM-08 prep
# package. No remote access. No production touch.
#
# Anchors:
#   G-IAM-08, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12
#
# Exit codes:
#   0 — all checks PASS
#   1 — at least one check FAIL

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLAN="${ROOT_DIR}/G-IAM-08-MIGRATION-PLAN.md"
DROPIN="${ROOT_DIR}/keycloak.service.d/g-iam-08-fix.conf.template"
PASSWORD_TEMPLATE="${ROOT_DIR}/db.password.template"
RUNBOOK="${ROOT_DIR}/OPERATOR-RUNBOOK-G-IAM-08.md"
INSTALLER="${ROOT_DIR}/install-db-password-file.sh"

pass_count=0
fail_count=0

check() {
    local label=$1
    shift
    if "$@"; then
        echo "  [PASS] ${label}"
        pass_count=$((pass_count + 1))
    else
        echo "  [FAIL] ${label}"
        fail_count=$((fail_count + 1))
    fi
}

exists() { [[ -f "$1" ]]; }
contains() { grep -q -- "$2" "$1"; }
not_contains() { ! grep -q -- "$2" "$1"; }
# not_contains_noncomment: like not_contains, but ignores commented lines
# (lines whose first non-blank character is '#'). Used to assert that the
# active config in a template doesn't contain a forbidden token even when
# a header comment quotes it for explanatory purposes.
not_contains_noncomment() {
    ! grep -v '^[[:space:]]*#' "$1" | grep -q -- "$2"
}

echo "G-IAM-08 prep-package offline validation"
echo "----------------------------------------"

echo "[1] File presence"
check "migration plan present"   exists "$PLAN"
check "systemd drop-in template present" exists "$DROPIN"
check "password file template present"   exists "$PASSWORD_TEMPLATE"
check "operator runbook present"         exists "$RUNBOOK"
check "installer script present"         exists "$INSTALLER"

echo "[2] systemd drop-in template content"
check "template uses --db-password-file=/etc/keycloak/db.password" \
    contains "$DROPIN" "--db-password-file=/etc/keycloak/db.password"
check "template active config does NOT contain --db-password=<literal> flag" \
    not_contains_noncomment "$DROPIN" "--db-password=[^f]"
check "template references G-IAM-08 in header" \
    contains "$DROPIN" "G-IAM-08"

echo "[3] Migration plan content"
check "plan references G-IAM-08" \
    contains "$PLAN" "G-IAM-08"
check "plan records the 2026-05-12 verified evidence timestamp" \
    contains "$PLAN" "2026-05-12 07:37:50Z"
check "plan includes a Rollback section" \
    contains "$PLAN" "Rollback"
check "plan includes HITL gate language" \
    contains "$PLAN" "HITL"

echo "[4] Runbook content"
check "runbook references G-IAM-08" \
    contains "$RUNBOOK" "G-IAM-08"
check "runbook contains explicit non-deploy statement" \
    contains "$RUNBOOK" "does NOT deploy"
check "runbook includes operator sign-off block" \
    contains "$RUNBOOK" "sign-off"

echo "[5] Installer script sanity"
check "installer has set -euo pipefail" \
    contains "$INSTALLER" "set -euo pipefail"
check "installer does NOT echo secrets via cat target" \
    not_contains "$INSTALLER" "cat \"\${TARGET_FILE}\""

echo "----------------------------------------"
echo "Summary: ${pass_count} PASS / ${fail_count} FAIL"

if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
