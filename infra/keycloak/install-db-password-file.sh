#!/usr/bin/env bash
# install-db-password-file.sh — install Keycloak DB password file in place.
#
# Idempotent installer for the G-IAM-08 mitigation.
# Usage:
#   ./install-db-password-file.sh <source-file> <target-dir>
#
# - <source-file> : path to the operator-prepared password file (a single
#                   line, no trailing newline beyond the password value).
# - <target-dir>  : destination directory (default usage: /etc/keycloak).
#                   The script writes the password to <target-dir>/db.password.
#
# After install:
#   * mode  0640
#   * owner root:keycloak  (skipped with warning if not run as root)
#   * directory created if missing
#
# Anchors:
#   G-IAM-08, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12
#
# No secret values are echoed to stdout.

set -euo pipefail

usage() {
    echo "Usage: $0 <source-file> <target-dir>" >&2
    exit 2
}

[[ $# -eq 2 ]] || usage

SRC=$1
TARGET_DIR=$2
TARGET_FILE="${TARGET_DIR}/db.password"

if [[ ! -f "$SRC" ]]; then
    echo "ERROR: source file not found: $SRC" >&2
    exit 1
fi

if [[ ! -s "$SRC" ]]; then
    echo "ERROR: source file is empty: $SRC" >&2
    exit 1
fi

# Create target dir if missing (mode 0755 for the dir is conventional).
if [[ ! -d "$TARGET_DIR" ]]; then
    install -d -m 0755 "$TARGET_DIR"
fi

# Install via umask-safe `install` to apply mode atomically.
install -m 0640 "$SRC" "$TARGET_FILE"

# Set ownership to root:keycloak when running as root; otherwise warn.
if [[ "$(id -u)" -eq 0 ]]; then
    chown root:keycloak "$TARGET_FILE"
else
    echo "WARNING: not running as root; skipping chown root:keycloak on ${TARGET_FILE}." >&2
    echo "         Re-run as root or run: sudo chown root:keycloak ${TARGET_FILE}" >&2
fi

# Resulting metadata only (no contents).
ls -l "$TARGET_FILE"
