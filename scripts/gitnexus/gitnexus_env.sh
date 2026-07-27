#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# gitnexus_env.sh — GitNexus code-contour environment for banxe-emi-stack
# (PHASE0/PHASE1 bootstrap, sandbox-scope; ported from banxe-architecture
# GITNEXUS01 phase1 — see docs/canon/GITNEXUS-PHASE1-EMI-STACK-CODE-CONTOUR.md).
#
# LICENSE DISCLAIMER: GitNexus is licensed under PolyForm-Noncommercial-1.0.0.
#   Sandbox/TRAINING use only without a license. PROD/commercial use requires
#   a purchased GitNexus license (banxe-architecture STEP15 PHASE0-VERIFY gate).
#
# BANXE_ENV=sandbox · data_class=TRAINING · PROD_READY=false
# Idempotent: safe to source multiple times. NO-MOCK: no graph data is faked.
# This repo's PHASE1 contour is STRUCTURAL ONLY — it never invokes an external
# GitNexus engine (governance + impact contour bootstrap, no runtime AI agents).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

export GITNEXUS_ENV="${GITNEXUS_ENV:-sandbox}"

# EX_CONFIG per sysexits.h — "MCP not connected" contract code (shared fleet-wide)
GITNEXUS_EX_CONFIG=78

# gitnexus_guard — fail-closed outside sandbox (license boundary).
# Returns 0 in sandbox; prints disclaimer and returns 1 otherwise.
gitnexus_guard() {
  if [ "${GITNEXUS_ENV}" != "sandbox" ]; then
    echo "GitNexus license: PolyForm-Noncommercial-1.0.0." >&2
    echo "PROD/commercial use requires a purchased GitNexus license." >&2
    echo "GITNEXUS_ENV=${GITNEXUS_ENV} is not 'sandbox' — fail-closed." >&2
    return 1
  fi
  return 0
}

# gitnexus_probe — detect live MCP availability WITHOUT network calls.
# Informational only in this repo (PHASE1 here never delegates to the engine):
# criteria (both local): GITNEXUS_MCP_ENDPOINT set AND `gitnexus` binary on PATH.
gitnexus_probe() {
  if [ -n "${GITNEXUS_MCP_ENDPOINT:-}" ] && command -v gitnexus >/dev/null 2>&1; then
    return 0
  fi
  echo "GitNexus MCP not connected — structural contour only (no graph enrich)" >&2
  return "${GITNEXUS_EX_CONFIG}"
}
