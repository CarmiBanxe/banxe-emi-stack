#!/usr/bin/env bash
# gen-docs.sh — auto-generate API documentation from docstrings (pdoc).
# Factory duty (operating-mode.md): the Factory documents the code it builds.
# "Documentation parallel to code": docstrings -> HTML docs, regenerated on demand.
#
# Usage: bash scripts/gen-docs.sh            # full generation into docs/api/
#        bash scripts/gen-docs.sh --check    # report doc coverage, no write
#
# Output docs/api/ is generated (gitignored) — regenerate, don't hand-edit.
set -uo pipefail
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
PDOC="$ROOT/.venv/bin/pdoc"
OUT="$ROOT/docs/api"

[ -x "$PDOC" ] || { echo "❌ pdoc not found in .venv (run: .venv/bin/pip install pdoc)"; exit 1; }

if [ "${1:-}" = "--check" ]; then
    echo "=== docstring coverage (module-level) ==="
    "$ROOT/.venv/bin/python" - <<'PY'
import ast, pathlib
roots = ["services", "api", "src"]
tot = documented = 0
for r in roots:
    for f in pathlib.Path(r).rglob("*.py"):
        if "__pycache__" in str(f) or f.stat().st_size == 0:
            continue
        tot += 1
        try:
            if ast.get_docstring(ast.parse(f.read_text())):
                documented += 1
        except Exception:
            pass
print(f"modules={tot} with_module_docstring={documented} coverage={documented*100//max(tot,1)}%")
PY
    exit 0
fi

echo "📚 Generating API docs from docstrings -> $OUT"
mkdir -p "$OUT"
# pdoc imports modules; isolate failures so one bad import doesn't abort the whole run.
# Generate per top-level package; collect failures without failing the build.
FAILED=0
for pkg in services api src; do
    [ -d "$pkg" ] || continue
    echo "→ $pkg"
    if ! "$PDOC" "$pkg" -o "$OUT" 2>"$OUT/.pdoc-$pkg.log"; then
        echo "  ⚠️  some $pkg modules failed to import (see docs/api/.pdoc-$pkg.log) — partial docs kept"
        FAILED=1
    fi
done
echo "--- generated files ---"
find "$OUT" -name '*.html' | wc -l | sed 's/^/html_pages=/'
echo "✅ docs generated (partial=$FAILED). Open docs/api/index.html"
