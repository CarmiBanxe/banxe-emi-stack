#!/usr/bin/env bash
# provision-clients.sh — Provision client_secrets for 4 EMI service accounts
# ADR-017 / I-34 / INV-IAM-01 | FCA CASS 15
#
# ENV-driven; do not run before GATE-A; do not commit real secrets.
# All secrets read from operator-supplied environment variables.
#
# Prerequisites:
#   - Keycloak is running and healthy at ${KC_BASE_URL:-http://evo1:8180}
#   - Realm banxe-emi has been imported (banxe-emi-realm.json)
#   - KC_BOOT_ADMIN, KC_BOOT_ADMIN_PASSWORD, KC_CLIENT_SECRET_* are exported
#
# Usage (from evo1, after GATE-A + realm import):
#   source ~/.banxe/keycloak.env
#   bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/provision-clients.sh

set -euo pipefail

KC_BASE_URL="${KC_BASE_URL:-http://localhost:8180}"
REALM="banxe-emi"

# Detect whether we're running against Docker container or native KC
if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "keycloak-banxe-emi"; then
  KCADM="docker exec -i keycloak-banxe-emi /opt/keycloak/bin/kcadm.sh"
elif [ -x "/home/banxe/keycloak-26.2.5/bin/kcadm.sh" ]; then
  KCADM="/home/banxe/keycloak-26.2.5/bin/kcadm.sh"
else
  echo "ERROR: kcadm.sh not found. Ensure Keycloak is running." >&2
  exit 1
fi

# Validate required env vars
required_vars=(
  KC_BOOT_ADMIN
  KC_BOOT_ADMIN_PASSWORD
  KC_CLIENT_SECRET_BANXE_COMPLIANCE_API
  KC_CLIENT_SECRET_BANXE_DASHBOARD
  KC_CLIENT_SECRET_DEEP_SEARCH
  KC_CLIENT_SECRET_DRIVE_WATCHER
)
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: Required env var $var is not set." >&2
    exit 2
  fi
done

echo "=== Authenticating with Keycloak admin ==="
$KCADM config credentials \
  --server "${KC_BASE_URL}" \
  --realm master \
  --user "${KC_BOOT_ADMIN}" \
  --password "${KC_BOOT_ADMIN_PASSWORD}"

echo "=== Provisioning client_secrets for realm ${REALM} ==="

declare -A CLIENT_SECRETS=(
  ["banxe-compliance-api"]="${KC_CLIENT_SECRET_BANXE_COMPLIANCE_API}"
  ["banxe-dashboard"]="${KC_CLIENT_SECRET_BANXE_DASHBOARD}"
  ["deep-search"]="${KC_CLIENT_SECRET_DEEP_SEARCH}"
  ["drive_watcher"]="${KC_CLIENT_SECRET_DRIVE_WATCHER}"
)

for client_id in "${!CLIENT_SECRETS[@]}"; do
  secret="${CLIENT_SECRETS[$client_id]}"
  echo "--- Provisioning: $client_id"

  # Get internal Keycloak UUID for this clientId
  cid=$($KCADM get clients -r "${REALM}" -q "clientId=${client_id}" \
        --fields id --format csv --noquotes | tail -1)

  if [ -z "$cid" ]; then
    echo "ERROR: Client '$client_id' not found in realm '${REALM}'. Run import-realm.sh first." >&2
    exit 3
  fi

  $KCADM update "clients/${cid}" -r "${REALM}" -s "secret=${secret}"
  echo "PROVISIONED: $client_id (uuid=$cid)"
done

echo ""
echo "=== Provision complete. Verify with scripts/healthcheck.sh smoke-test. ==="
