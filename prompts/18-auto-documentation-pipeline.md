# Prompt 18: Auto-Documentation Pipeline
## Claude Code Implementation Prompt for Legion

---

## TASK
Implement a complete auto-documentation pipeline for the Banxe AI Bank project that automatically generates, maintains, and publishes professional developer documentation.

## CONTEXT
- **Repository:** banxe-emi-stack (refactor/claude-ai-scaffold branch)
- **Architecture repo:** banxe-architecture (main branch)
- **Stack:** Python 3.12, FastAPI, PostgreSQL, Docker
- **Docs tools:** MkDocs Material, pdoc, Sphinx, commitizen
- **CI:** GitHub Actions

## REQUIREMENTS

### 1. FastAPI OpenAPI Enhancement
```python
# api/main.py - Enhance FastAPI app configuration
app = FastAPI(
    title="Banxe AI Bank API",
    description="EMI Financial Analytics Stack - FCA CASS 15 P0",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Onboarding", "description": "KYC/KYB customer onboarding"},
        {"name": "Payments", "description": "SEPA/SWIFT/FPS payment processing"},
        {"name": "Compliance", "description": "AML/Sanctions screening"},
        {"name": "Accounts", "description": "Account management"},
        {"name": "Crypto", "description": "Crypto wallet and trading"},
        {"name": "Monitoring", "description": "Transaction monitoring"},
        {"name": "Reports", "description": "Regulatory reporting"},
        {"name": "Agents", "description": "AI agent management"},
        {"name": "Health", "description": "System health checks"},
    ]
)
```

**Action items:**
- [ ] Add OpenAPI tags to all existing routes
- [ ] Add Pydantic model docstrings with Field descriptions
- [ ] Add response_model to all endpoints
- [ ] Add example values to all Field definitions
- [ ] Create `/api/v1/docs/export` endpoint for OpenAPI JSON export

### 2. Python Docstring Standards
Ensure ALL modules, classes, and functions have Google-style docstrings:
```python
# Every module must have:
"""Module description.

This module handles [specific domain].
Part of the [department] department.

Attributes:
    MODULE_VAR: Description.
"""

# Every class must have:
class PaymentProcessor:
    """Process outbound and inbound payments.

    Handles SEPA, SWIFT, and Faster Payments processing
    with integrated sanctions screening and AML checks.

    Attributes:
        payment_rail: Active payment rail connection.
        screening_engine: Sanctions screening integration.
    """
```

**Action items:**
- [ ] Audit all .py files for missing docstrings
- [ ] Add module-level docstrings to all files
- [ ] Add class-level docstrings to all classes
- [ ] Add function docstrings with Args/Returns/Raises

### 3. pdoc Configuration
Create `docs/conf.py` for automated API doc generation:
```python
# docs/conf.py
import pdoc

modules = [
    "api",
    "agents",
    "banxe_mcp",
]

pdoc.render.configure(
    docformat="google",
    show_source=True,
)
```

**Action items:**
- [ ] Create `docs/conf.py`
- [ ] Add `pdoc` to requirements-docs.txt
- [ ] Create `scripts/generate-api-docs.sh`
- [ ] Add to pre-commit hooks

### 4. Commitizen Setup
```toml
# pyproject.toml additions
[tool.commitizen]
name = "cz_conventional_commits"
version = "0.2.0"
tag_format = "v$version"
changelog_file = "CHANGELOG.md"
update_changelog_on_bump = true
major_version_zero = true

[tool.commitizen.customize]
commit_parser = "^(?P<change_type>feat|fix|docs|refactor|test|ci|infra|chore|perf|security|compliance)(?:\\((?P<scope>[^)]+)\\))?!?:\\s(?P<message>.+)"
```

**Action items:**
- [ ] Add commitizen config to pyproject.toml
- [ ] Install pre-commit hook for commit-msg validation
- [ ] Generate initial CHANGELOG.md
- [ ] Create `scripts/release.sh` for version bumping

### 5. GitHub Actions CI for Docs
```yaml
# .github/workflows/api-docs.yml
name: Generate API Documentation
on:
  push:
    branches: [refactor/claude-ai-scaffold]
    paths: ['**/*.py']
jobs:
  generate-docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install pdoc
      - run: pdoc --html --output-dir docs/api api agents banxe_mcp
      - run: python -c "from api.main import app; import json; print(json.dumps(app.openapi(), indent=2))" > docs/openapi.json
```

**Action items:**
- [ ] Create `.github/workflows/api-docs.yml`
- [ ] Add OpenAPI export script
- [ ] Configure artifact upload

### 6. Claude Hook Enhancement
Update `.claude/hooks/` to include documentation checks:

```bash
# .claude/hooks/post-edit-docs.sh
#!/bin/bash
# Auto-update docs when code changes
CHANGED_FILES=$(git diff --name-only HEAD)

if echo "$CHANGED_FILES" | grep -q '\.py$'; then
    echo "Python files changed, regenerating API docs..."
    pdoc --html --output-dir docs/api api agents banxe_mcp 2>/dev/null || true
fi

if echo "$CHANGED_FILES" | grep -q 'api/'; then
    echo "API files changed, exporting OpenAPI schema..."
    python -c "from api.main import app; import json; f=open('docs/openapi.json','w'); json.dump(app.openapi(), f, indent=2)" 2>/dev/null || true
fi
```

**Action items:**
- [ ] Create post-edit-docs.sh hook
- [ ] Register in .claude/hooks/
- [ ] Test with sample code changes

## INFRASTRUCTURE CHECKLIST
```
INFRASTRUCTURE CHECKLIST — Auto-Documentation Pipeline
[ ] LucidShark scan clean
[ ] Semgrep rules added (docs coverage check)
[ ] Claude Rules coverage (.claude/rules/docs-standards.md)
[ ] Claude Commands created (/docs-status)
[ ] AI Agent Soul files (docs-agent)
[ ] Agent Workflow (docs-generation)
[ ] Orchestrator registration
[ ] MCP Server tools (docs endpoints)
[ ] AI Registry (docs-agent registered)
[ ] n8n Workflows (docs build notification)
[ ] Docker services (mkdocs serve container)
[ ] dbt models (docs metrics)
[ ] Grafana dashboard (docs health)
[ ] Tests passing (docs generation tests)
```

## ACCEPTANCE CRITERIA
- [ ] `mkdocs serve` renders all architecture docs correctly
- [ ] `pdoc` generates API reference from all Python modules
- [ ] FastAPI `/docs` shows all endpoints with descriptions
- [ ] `cz changelog` generates valid CHANGELOG.md
- [ ] GitHub Actions deploys docs on push to main
- [ ] Pre-commit hook validates commit message format
- [ ] Claude post-edit hook regenerates docs on code change
- [ ] All Python files have Google-style docstrings

## CROSS-REFERENCES
- `banxe-architecture/mkdocs.yml` (MkDocs config)
- `banxe-architecture/docs/DEV-DOCUMENTATION-GUIDE.md` (dev guide)
- `banxe-architecture/docs/CHANGELOG-POLICY.md` (commit conventions)
- `banxe-architecture/.github/workflows/docs.yml` (CI pipeline)
- `.claude/CLAUDE.md` (Infrastructure Checklist - CANON)
