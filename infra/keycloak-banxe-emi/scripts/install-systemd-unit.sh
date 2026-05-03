#!/usr/bin/env bash
# install-systemd-unit.sh — Wrap existing Keycloak 26.2.5 as --user systemd service
# ADR-017 / I-34 | FCA CASS 15
#
# Purpose: Fixes I-34 violation (DB password visible in `ps aux`) by moving secrets
# to a EnvironmentFile that is mode 600 and not accessible to other processes.
#
# Prerequisites:
#   - Keycloak 26.2.5 installed at /home/banxe/keycloak-26.2.5/
#   - systemd --user available for user `banxe`
#   - ~/.banxe/keycloak.env exists and contains secrets (mode 600)
#
# Usage (as user `banxe` on evo1):
#   bash /data/banxe/banxe-emi-stack/infra/keycloak-banxe-emi/scripts/install-systemd-unit.sh
#
# After install:
#   systemctl --user enable --now keycloak-banxe-emi
#   systemctl --user status keycloak-banxe-emi

set -euo pipefail

KC_HOME="${KC_HOME:-/home/banxe/keycloak-26.2.5}"
KC_ENV_FILE="${KC_ENV_FILE:-${HOME}/.banxe/keycloak.env}"
UNIT_DIR="${HOME}/.config/systemd/user"
UNIT_FILE="${UNIT_DIR}/keycloak-banxe-emi.service"

if [ ! -d "${KC_HOME}/bin" ]; then
  echo "ERROR: Keycloak not found at ${KC_HOME}" >&2
  exit 1
fi

if [ ! -f "${KC_ENV_FILE}" ]; then
  echo "ERROR: Environment file not found: ${KC_ENV_FILE}" >&2
  echo "       Create it with mode 600 and KC_BOOT_ADMIN, KC_BOOT_ADMIN_PASSWORD, KC_DB_PASSWORD." >&2
  exit 2
fi

# Enforce I-34: env file must not be world-readable
env_perms=$(stat -c "%a" "${KC_ENV_FILE}")
if [ "${env_perms}" != "600" ] && [ "${env_perms}" != "400" ]; then
  echo "I-34 VIOLATION: ${KC_ENV_FILE} has mode ${env_perms} — must be 600." >&2
  echo "Run: chmod 600 ${KC_ENV_FILE}" >&2
  exit 3
fi

mkdir -p "${UNIT_DIR}"

cat > "${UNIT_FILE}" <<EOF
[Unit]
Description=Keycloak 26.2.5 — Banxe EMI IAM (ADR-017)
After=network.target postgresql.service
Wants=network.target

[Service]
Type=simple
User=${USER}

# I-34: secrets loaded from EnvironmentFile (mode 600), NOT from CLI args
EnvironmentFile=${KC_ENV_FILE}

Environment=KC_HTTP_PORT=8180
Environment=KC_HOSTNAME=evo1
Environment=KC_DB=postgres
Environment=KC_DB_URL=jdbc:postgresql://127.0.0.1:15433/keycloak
Environment=KC_DB_USERNAME=keycloak
# KC_DB_PASSWORD must be set in EnvironmentFile — never here
Environment=KC_LOG_LEVEL=INFO
Environment=KC_HEALTH_ENABLED=true
Environment=KC_METRICS_ENABLED=false
Environment=KC_HTTP_ENABLED=true
Environment=KC_HOSTNAME_STRICT=false

ExecStart=${KC_HOME}/bin/kc.sh start --optimized --http-port=\${KC_HTTP_PORT}
ExecStop=/bin/kill -SIGTERM \$MAINPID

Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=keycloak-banxe-emi

[Install]
WantedBy=default.target
EOF

echo "=== Unit file written: ${UNIT_FILE} ==="

systemctl --user daemon-reload
echo "=== systemd daemon reloaded ==="

echo ""
echo "Next steps:"
echo "  1. Verify env file: grep -c KC_DB_PASSWORD ${KC_ENV_FILE}"
echo "  2. Enable + start: systemctl --user enable --now keycloak-banxe-emi"
echo "  3. Check status:   systemctl --user status keycloak-banxe-emi"
echo "  4. Check logs:     journalctl --user -u keycloak-banxe-emi -f"
echo "  5. Health check:   bash scripts/healthcheck.sh http://evo1:8180"
echo ""
echo "=== install-systemd-unit.sh done. GATE-A remediation complete for I-34. ==="
