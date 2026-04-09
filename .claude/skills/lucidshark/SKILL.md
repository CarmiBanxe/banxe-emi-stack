---
name: lucidshark
description: "Unified code quality and security scanner: linting, type checking, formatting, security (SAST/SCA/IaC/container), testing, coverage, duplication. Run proactively after code changes."
---

# LucidShark - Unified Code Quality and Security Scanner

Run scans proactively after code changes. Don't wait for user to ask.

## IMPORTANT: Init vs Autoconfigure

**Two different commands, two different purposes:**

| Command | Purpose | When to Use |
|---------|---------|-------------|
| `lucidshark init` | Configure Claude Code integration (`.mcp.json`, `.claude/` files) | Once per project, to enable MCP tools |
| `mcp__lucidshark__autoconfigure` | Generate `lucidshark.yml` configuration | When user asks to "autoconfigure lucidshark" or "set up lucidshark config" |

**User says** "autoconfigure lucidshark" → **Call** `mcp__lucidshark__autoconfigure` MCP tool (NOT `lucidshark init`)

## What It Can Do

| Domain | What It Does | Tools |
|--------|--------------|-------|
| **linting** | Style issues, code smells, auto-fix | Ruff, ESLint, Biome, Clippy, Checkstyle, PMD |
| **type_checking** | Type errors, static analysis | mypy, Pyright, tsc, SpotBugs, cargo check |
| **sast** | Security vulnerabilities in code | OpenGrep |
| **sca** | Dependency vulnerabilities | Trivy |
| **iac** | Infrastructure misconfigurations | Checkov |
| **container** | Container image vulnerabilities | Trivy |
| **testing** | Run tests, report failures | pytest, Jest, Karma, Playwright, JUnit, cargo test |
| **coverage** | Code coverage analysis | coverage.py, Istanbul, JaCoCo, Tarpaulin |
| **formatting** | Code formatting checks, auto-fix | ruff format, Prettier, rustfmt |
| **duplication** | Detect code clones | Duplo |

## When to Scan

| Trigger | MCP Tool | CLI Alternative (Binary / Pip) |
|---------|----------|-----------------|
| After editing code | `mcp__lucidshark__scan(fix=true)` | `./lucidshark scan --fix --format ai` / `lucidshark scan --fix --format ai` |
| After fixing bugs | `mcp__lucidshark__scan(fix=true)` | `./lucidshark scan --fix --format ai` / `lucidshark scan --fix --format ai` |
| User asks to run tests | `mcp__lucidshark__scan(domains=["testing"])` | `./lucidshark scan --testing --format ai` / `lucidshark scan --testing --format ai` |
| User asks about coverage | `mcp__lucidshark__scan(domains=["testing","coverage"])` | `./lucidshark scan --testing --coverage --format ai` / `lucidshark scan --testing --coverage --format ai` |
| Security concerns | `mcp__lucidshark__scan(domains=["sast","sca"])` | `./lucidshark scan --sast --sca --format ai` / `lucidshark scan --sast --sca --format ai` |
| Before commits | `mcp__lucidshark__scan(domains=["all"])` | `./lucidshark scan --all --format ai` / `lucidshark scan --all --format ai` |

**Skip scanning** if user explicitly says "don't scan" or "skip checks".

## Smart Domain Selection

Pick domains based on what files changed:

| Files Changed | MCP domains | CLI flags |
|---|---|---|
| `.py`, `.js`, `.ts`, `.rs`, `.go`, `.java`, `.kt` | `["linting","type_checking","formatting"]` | `--linting --type-checking --formatting` |
| `Dockerfile`, `docker-compose.*` | `["container"]` | `--container` |
| `.tf`, `.yaml`/`.yml` (k8s/CloudFormation) | `["iac"]` | `--iac` |
| `package.json`, `requirements.txt`, `Cargo.toml`, `go.mod` | `["sca"]` | `--sca` |
| Auth, crypto, input handling, SQL code | `["sast"]` | `--sast` |
| Mixed / many file types / before commit | `["all"]` | `--all` |

## MCP Tools

```
mcp__lucidshark__scan(fix=true)                                # Default: auto-fix + changed files
mcp__lucidshark__scan(domains=["linting","type_checking"])      # Targeted domains
mcp__lucidshark__scan(domains=["testing"])                      # Run tests
mcp__lucidshark__scan(domains=["testing","coverage"])           # Tests + coverage
mcp__lucidshark__scan(domains=["sast","sca"])                   # Security scan
mcp__lucidshark__scan(domains=["all"])                          # Full scan
mcp__lucidshark__scan(files=["path/to/file.py"])                # Specific files
mcp__lucidshark__scan(all_files=true)                           # All files (not just changed)
mcp__lucidshark__check_file(file_path="path/to/file.py")       # Check single file
mcp__lucidshark__get_fix_instructions(issue_id="ISSUE_ID")     # Get fix details
mcp__lucidshark__apply_fix(issue_id="ISSUE_ID")                # Auto-fix an issue
```

## CLI Commands

**Binary users:** Use `./lucidshark` (installed via install.sh)
**Pip users:** Use `lucidshark` (installed in PATH)

```bash
# Default after code changes (auto-fixes linting)
./lucidshark scan --fix --format ai

# Run tests
./lucidshark scan --testing --format ai

# Check test coverage (requires testing)
./lucidshark scan --testing --coverage --format ai

# Security scan (code + dependencies)
./lucidshark scan --sast --sca --format ai

# Full scan including tests, coverage, duplication
./lucidshark scan --all --format ai

# Scan specific files
./lucidshark scan --files path/to/file.py --format ai

# PR/CI: filter to files changed since main, with strict thresholds
./lucidshark scan --all --base-branch origin/main \
  --coverage-threshold-scope both \
  --duplication-threshold-scope both
```

**Default:** Scans only uncommitted changes. Use `--all-files` for full project.

## Threshold Scope for CI/PR Workflows

When using `--base-branch` for incremental PR checks:

| Scope | Behavior |
|-------|----------|
| `changed` (default) | Threshold applies to changed files only. **Warning:** Can let project-wide metrics creep up over time. |
| `project` | Threshold applies to full project. |
| `both` | Threshold applies to both. Fail if **either** exceeds threshold. **Recommended for strict quality gates.** |

```bash
# Prevent duplication/coverage from creeping up over time
./lucidshark scan --all --base-branch origin/main \  # binary install
  --duplication-threshold-scope both \
  --coverage-threshold-scope both

# Or with pip install:
lucidshark scan --all --base-branch origin/main \
  --duplication-threshold-scope both \
  --coverage-threshold-scope both
```

## Workflow

1. Make code changes
2. Run `mcp__lucidshark__scan(fix=true)` or `./lucidshark scan --fix --format ai` (binary) / `lucidshark scan --fix --format ai` (pip)
3. Fix remaining issues
4. Re-scan if needed
5. Report done

**Task is complete when scan shows zero issues.**
