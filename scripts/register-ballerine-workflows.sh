#!/usr/bin/env bash
# register-ballerine-workflows.sh — Register Banxe KYC/KYB workflow definitions in Ballerine
# IL-058 | S5-13 | FCA MLR 2017 §18 CDD requirement | banxe-emi-stack
#
# Run ONCE after first deploy (or after wipe) to seed workflow definitions.
# Idempotent: checks if definition already exists before registering.
#
# Usage (from Legion):
#   cd ~/banxe-emi-stack
#   bash scripts/register-ballerine-workflows.sh
#
# Requires:
#   BALLERINE_URL  — Ballerine API base (default: http://gmktec:3000)
#   BALLERINE_AUTH_TOKEN — Ballerine API token (optional, if auth enabled)
#
# After registration, set in .env:
#   BALLERINE_KYC_DEFINITION_ID=banxe-individual-kyc-v1
#   BALLERINE_KYB_DEFINITION_ID=banxe-business-kyb-v1

set -euo pipefail

BALLERINE_URL="${BALLERINE_URL:-http://gmktec:3000}"
AUTH_TOKEN="${BALLERINE_AUTH_TOKEN:-}"
DEFINITIONS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../infra/ballerine/workflow-definitions" && pwd)"

RED="\033[0;31m" GREEN="\033[0;32m" YELLOW="\033[1;33m" BOLD="\033[1m" RESET="\033[0m"

echo ""
echo -e "${BOLD}═══ Ballerine Workflow Registration ══════════════════${RESET}"
echo -e "  URL:  ${BALLERINE_URL}"
echo -e "  Defs: ${DEFINITIONS_DIR}"
echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
echo ""

# ── Build auth header ─────────────────────────────────────────────────────────
AUTH_HEADER=""
if [[ -n "$AUTH_TOKEN" ]]; then
    AUTH_HEADER="Authorization: Bearer ${AUTH_TOKEN}"
fi

# ── Health check ──────────────────────────────────────────────────────────────
echo -n "  Checking Ballerine health... "
if ! curl -sf "${BALLERINE_URL}/api/v1/health" -o /dev/null 2>/dev/null; then
    echo -e "${RED}FAIL${RESET}"
    echo ""
    echo -e "  ${RED}ERROR:${RESET} Ballerine not reachable at ${BALLERINE_URL}"
    echo "  Is it running? Try: ssh gmktec 'docker ps | grep ballerine'"
    echo "  Deploy with: cd ~/banxe-emi-stack/infra/ballerine && docker compose up -d"
    exit 1
fi
echo -e "${GREEN}OK${RESET}"

# ── Register a workflow definition ───────────────────────────────────────────
register_definition() {
    local def_file="$1"
    local def_id
    def_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" < "$def_file")

    echo -n "  Registering ${def_id}... "

    # Check if already exists
    local existing_status
    if [[ -n "$AUTH_HEADER" ]]; then
        existing_status=$(curl -sf -o /dev/null -w "%{http_code}" \
            -H "$AUTH_HEADER" \
            "${BALLERINE_URL}/api/v1/workflow-definition/${def_id}" 2>/dev/null || echo "000")
    else
        existing_status=$(curl -sf -o /dev/null -w "%{http_code}" \
            "${BALLERINE_URL}/api/v1/workflow-definition/${def_id}" 2>/dev/null || echo "000")
    fi

    if [[ "$existing_status" == "200" ]]; then
        echo -e "${YELLOW}ALREADY EXISTS (skip)${RESET}"
        return 0
    fi

    # Register via POST
    local http_status
    if [[ -n "$AUTH_HEADER" ]]; then
        http_status=$(curl -sf -o /tmp/ballerine-reg-out.json -w "%{http_code}" \
            -X POST "${BALLERINE_URL}/api/v1/workflow-definition" \
            -H "Content-Type: application/json" \
            -H "$AUTH_HEADER" \
            -d @"$def_file" 2>/dev/null || echo "000")
    else
        http_status=$(curl -sf -o /tmp/ballerine-reg-out.json -w "%{http_code}" \
            -X POST "${BALLERINE_URL}/api/v1/workflow-definition" \
            -H "Content-Type: application/json" \
            -d @"$def_file" 2>/dev/null || echo "000")
    fi

    if [[ "$http_status" == "201" || "$http_status" == "200" ]]; then
        echo -e "${GREEN}REGISTERED (${http_status})${RESET}"
    else
        echo -e "${RED}FAIL (HTTP ${http_status})${RESET}"
        if [[ -f /tmp/ballerine-reg-out.json ]]; then
            echo "  Response: $(cat /tmp/ballerine-reg-out.json 2>/dev/null | head -c 300)"
        fi
        return 1
    fi
}

# ── Register all definitions ──────────────────────────────────────────────────
FAIL=0
for def_file in "${DEFINITIONS_DIR}"/*.json; do
    register_definition "$def_file" || FAIL=1
done

echo ""
echo -e "${BOLD}───────────────────────────────────────────────────────${RESET}"
if [[ $FAIL -eq 0 ]]; then
    echo -e "  ${BOLD}RESULT: ${GREEN}✅ All workflow definitions registered${RESET}"
    echo ""
    echo "  Add to banxe-emi-stack/.env:"
    echo "    BALLERINE_KYC_DEFINITION_ID=banxe-individual-kyc-v1"
    echo "    BALLERINE_KYB_DEFINITION_ID=banxe-business-kyb-v1"
else
    echo -e "  ${BOLD}RESULT: ${RED}❌ Some definitions failed to register${RESET}"
    echo "  Check Ballerine logs: ssh gmktec 'docker logs ballerine-workflow --tail 50'"
fi
echo -e "${BOLD}═══════════════════════════════════════════════════════${RESET}"
echo ""

exit $FAIL
