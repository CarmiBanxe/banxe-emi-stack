#!/usr/bin/env bash
# install_grok_safe.sh — download-inspect-confirm-execute wrapper for the
# xAI Grok CLI installer (https://x.ai/cli/install.sh).
#
# This script NEVER pipes a remote script directly into bash. It always:
#   1. downloads the installer to a local file,
#   2. shows its size/checksum/a content summary,
#   3. requires an explicit CONFIRM=yes to actually execute it.
#
# Without CONFIRM=yes it stops after step 2 (inspection only) — safe to run
# any time, makes no system changes.
set -euo pipefail

URL="https://x.ai/cli/install.sh"
DEST="${TMPDIR:-/tmp}/grok-install-$$.sh"
UA="Mozilla/5.0 (X11; Linux x86_64) curl-install-check"

echo "=== install_grok_safe.sh ==="
echo "Source: $URL"
echo "Downloading to: $DEST (not executing yet)"

curl -fsSL -A "$UA" -o "$DEST" "$URL"

echo
echo "--- Download facts ---"
echo "Size: $(wc -c < "$DEST") bytes"
echo "SHA256: $(shasum -a 256 "$DEST" | awk '{print $1}')"
echo "First line: $(head -n1 "$DEST")"

echo
echo "--- What this installer does (static summary — verify yourself before trusting) ---"
echo "- Detects OS/arch, downloads a prebuilt 'grok' binary from x.ai (falls back to a Google"
echo "  Cloud Storage mirror if x.ai is unreachable)."
echo "- Verifies the downloaded binary runs (--version) before installing it."
echo "- Installs to \$HOME/.grok/bin (never system-wide, never sudo)."
echo "- Symlinks into ~/.local/bin or /usr/local/bin ONLY if that dir is already on PATH"
echo "  and writable."
echo "- Appends a PATH block to ~/.bashrc / ~/.zshrc / fish config (backs up the rc file"
echo "  first if it doesn't already have a prior grok-installer block)."
echo "- Generates shell completions under ~/.grok/completions."
echo "- Does NOT run 'grok login' — auth is a separate, manual step."
echo "- Reads GROK_DEPLOYMENT_KEY from env only if you set it; unset here, so this run"
echo "  uses no deployment key."

echo
echo "--- Auth check on this machine ---"
if env | grep -qE '^(GROK_|XAI_API_KEY)'; then
  echo "GROK_*/XAI_API_KEY: SET (will be used if present)"
else
  echo "GROK_*/XAI_API_KEY: not set — installer will not use a deployment key"
fi

echo
if [ "${CONFIRM:-}" != "yes" ]; then
  echo "CONFIRM != yes — stopping after inspection. No system changes made."
  echo "Installer script left at: $DEST (inspect/delete it yourself)"
  echo
  echo "To actually run it: CONFIRM=yes bash scripts/install_grok_safe.sh"
  exit 0
fi

echo "CONFIRM=yes — executing the installer now."
bash "$DEST"
echo
echo "Installed. Run: scripts/verify_grok_setup.sh"
