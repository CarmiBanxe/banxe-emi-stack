#!/usr/bin/env bash
# validate-g-iam-09-backup-prep.sh — offline lint for the G-IAM-09 prep
# package. No remote access. No execution of the wrapper. No production
# touch.
#
# Anchors:
#   G-IAM-09, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12
#
# Exit codes:
#   0  all checks PASS
#   1  at least one check FAIL

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
POLICY="${ROOT_DIR}/G-IAM-09-BACKUP-POLICY.md"
RUNBOOK="${ROOT_DIR}/OPERATOR-RUNBOOK-G-IAM-09-RESTORE-DRILL.md"
WRAPPER="${ROOT_DIR}/scripts/kc-backup.sh.template"
CRON="${ROOT_DIR}/cron.d/kc-backup.cron.template"
ENV_EXAMPLE="${ROOT_DIR}/examples/backup.env.example"
OFFHOST_EXAMPLE="${ROOT_DIR}/examples/offhost-target.example"

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
# not_contains_noncomment: ignore commented lines.
not_contains_noncomment() {
    ! grep -v '^[[:space:]]*#' "$1" | grep -q -- "$2"
}

echo "G-IAM-09 prep-package offline validation"
echo "----------------------------------------"

echo "[1] File presence"
check "backup policy present"            exists "$POLICY"
check "restore-drill runbook present"    exists "$RUNBOOK"
check "wrapper template present"         exists "$WRAPPER"
check "cron template present"            exists "$CRON"
check "env example present"              exists "$ENV_EXAMPLE"
check "off-host target example present"  exists "$OFFHOST_EXAMPLE"

echo "[2] Wrapper template content"
check "wrapper uses pg_dump -Fc"                 contains "$WRAPPER" "pg_dump -Fc"
check "wrapper uses password file (KC_DB_PASSWORD_FILE)" \
    contains "$WRAPPER" "KC_DB_PASSWORD_FILE"
check "wrapper does NOT carry plaintext --db-password=<literal>" \
    not_contains_noncomment "$WRAPPER" "--db-password=[^f]"
check "wrapper does NOT carry plaintext PGPASSWORD assignment in shell" \
    not_contains_noncomment "$WRAPPER" "PGPASSWORD=[^\"$]"
check "wrapper performs sha256 step"             contains "$WRAPPER" "sha256sum"
check "wrapper has off-host copy step"           contains "$WRAPPER" "OFFHOST_TARGET"
check "wrapper has retention rotation step"      contains "$WRAPPER" "RETENTION_DAYS"
check "wrapper has set -euo pipefail"            contains "$WRAPPER" "set -euo pipefail"
check "wrapper has gpg symmetric encrypt step"   contains "$WRAPPER" "gpg --batch"

echo "[3] Cron template content"
check "cron references wrapper path placeholder" contains "$CRON" "{{WRAPPER_PATH}}"
check "cron references log path placeholder"     contains "$CRON" "{{LOG_PATH}}"
check "cron has explicit deploy-after-approval comment" \
    contains "$CRON" "after Central + operator approval"

echo "[4] Policy doc content"
check "policy references G-IAM-09"               contains "$POLICY" "G-IAM-09"
check "policy references ADR-029"                contains "$POLICY" "ADR-029"
check "policy records evidence timestamp"        contains "$POLICY" "2026-05-12 07:37:50Z"
check "policy contains HITL gate section"        contains "$POLICY" "HITL gate"
check "policy contains rollback section"         contains "$POLICY" "Rollback"
check "policy contains alignment matrix"         contains "$POLICY" "alignment matrix"

echo "[5] Runbook content"
check "runbook references G-IAM-09"              contains "$RUNBOOK" "G-IAM-09"
check "runbook contains explicit non-deploy statement" \
    contains "$RUNBOOK" "does NOT perform a production restore"
check "runbook contains restore drill section"   contains "$RUNBOOK" "Drill steps"
check "runbook contains operator sign-off block" contains "$RUNBOOK" "sign-off"
check "runbook contains validation checklist"    contains "$RUNBOOK" "Validation checklist"

echo "----------------------------------------"
echo "Summary: ${pass_count} PASS / ${fail_count} FAIL"

if [[ "$fail_count" -gt 0 ]]; then
    exit 1
fi
