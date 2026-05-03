#!/usr/bin/env bash
# healthcheck.sh — Verify Keycloak realm banxe-emi is healthy and realm is accessible
# ADR-017 / I-35 | FCA CASS 15
#
# Usage: bash infra/keycloak-banxe-emi/scripts/healthcheck.sh [base_url]
# Default base_url: http://evo1:8180

set -euo pipefail

KC_BASE_URL="${1:-${KC_BASE_URL:-http://evo1:8180}}"
REALM="banxe-emi"
EXPECTED_ISSUER="${KC_BASE_URL}/realms/${REALM}"

echo "=== Keycloak health check: ${KC_BASE_URL} ==="

# 1. Health endpoint
echo "--- /health/ready"
curl -fsS "${KC_BASE_URL}/health/ready" | jq -e '.status == "UP"' > /dev/null
echo "OK"

# 2. Realm OIDC discovery
echo "--- realm ${REALM} OIDC discovery"
actual_issuer=$(curl -fsS "${KC_BASE_URL}/realms/${REALM}/.well-known/openid-configuration" \
  | jq -r '.issuer')
if [ "$actual_issuer" != "$EXPECTED_ISSUER" ]; then
  echo "ERROR: issuer mismatch. Expected: ${EXPECTED_ISSUER}  Got: ${actual_issuer}" >&2
  exit 1
fi
echo "Issuer: ${actual_issuer}"
echo "OK"

# 3. Token endpoint accessible
echo "--- token endpoint reachable"
token_endpoint=$(curl -fsS "${KC_BASE_URL}/realms/${REALM}/.well-known/openid-configuration" \
  | jq -r '.token_endpoint')
curl -fsS --max-time 5 -o /dev/null -w "HTTP %{http_code}" \
  -X POST "${token_endpoint}" -d "grant_type=client_credentials" \
  -d "client_id=HEALTH_CHECK" -d "client_secret=INVALID" 2>/dev/null \
  | grep -qE "HTTP (401|400)"
echo "OK (got expected 401/400 for invalid client)"

echo ""
echo "=== Keycloak realm ${REALM} HEALTHY ==="
