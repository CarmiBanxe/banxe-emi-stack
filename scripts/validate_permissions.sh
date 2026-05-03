#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

fail=0

while IFS=$'\t' read -r meta path; do
  mode="${meta%% *}"

  case "$path" in
    .githooks/*|.git/hooks/*)
      continue
      ;;
    .lucidshark/bin/*)
      continue
      ;;
    *.sh)
      if [[ "$mode" != "100755" ]]; then
        echo "ERROR: shell script must be executable in git index: $path (mode=$mode)"
        fail=1
      fi
      ;;
    *)
      if [[ "$mode" == "100755" ]]; then
        echo "ERROR: non-shell file should not be executable in git index: $path (mode=$mode)"
        fail=1
      fi
      ;;
  esac
done < <(git ls-files -s)

if [[ "$fail" -ne 0 ]]; then
  echo "Permission validation failed."
  exit 1
fi

echo "Permission validation passed."
