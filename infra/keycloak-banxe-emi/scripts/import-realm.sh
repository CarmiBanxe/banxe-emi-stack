#!/usr/bin/env bash
# import-realm.sh — Import banxe-emi realm into existing Keycloak instance via kcadm.sh
# ADR-017 / I-35 | FCA CASS 15
#
# ENV-driven; do not run before GATE-A; do not commit real secrets.
#
# Usage (on evo1 after KC is healthy):
#   source ~/.banxe/keycloak.env
#   bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/import-realm.sh

set -euo pipefail

KC_BASE_URL="${KC_BASE_URL:-http://localhost:8180}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REALM_JSON="${SCRIPT_DIR}/../realms/banxe-emi-realm.json"

required_vars=(KC_BOOT_ADMIN KC_BOOT_ADMIN_PASSWORD)
for var in "${required_vars[@]}"; do
  if [ -z "${!var:-}" ]; then
    echo "ERROR: Required env var $var is not set." >&2
    exit 2
  fi
done

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "keycloak-banxe-emi"; then
  KCADM="docker exec -i keycloak-banxe-emi /opt/keycloak/bin/kcadm.sh"
elif [ -x "/home/banxe/keycloak-26.2.5/bin/kcadm.sh" ]; then
  KCADM="/home/banxe/keycloak-26.2.5/bin/kcadm.sh"
else
  echo "ERROR: kcadm.sh not found." >&2
  exit 1
fi

echo "=== Authenticating with Keycloak admin ==="
$KCADM config credentials \
  --server "${KC_BASE_URL}" \
  --realm master \
  --user "${KC_BOOT_ADMIN}" \
  --password "${KC_BOOT_ADMIN_PASSWORD}"

echo "=== Checking if realm banxe-emi exists ==="
if $KCADM get realms/banxe-emi --fields realm 2>/dev/null | grep -q "banxe-emi"; then
  echo "Realm banxe-emi already exists — skipping import (idempotent)"
else
  echo "=== Importing realm from ${REALM_JSON} ==="
  $KCADM create realms -f "${REALM_JSON}"
  echo "Realm banxe-emi imported."
fi

echo ""
echo "=== Import done. Run provision-clients.sh next (GATE-B). ==="
