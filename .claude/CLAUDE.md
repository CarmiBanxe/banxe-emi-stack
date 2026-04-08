

<!-- lucidshark:start - managed by lucidshark init, do not edit manually -->
## LucidShark — REQUIRED: Scan After Every Code Change

**CRITICAL DISTINCTION**:
- **`lucidshark init`** = Configure Claude Code/IDE integration (`.mcp.json`, `.claude/` files). Run this ONCE per project.
- **`mcp__lucidshark__autoconfigure`** = Generate `lucidshark.yml` configuration (detect languages, install tools, configure scanners). Use when user asks to "autoconfigure lucidshark" or "set up lucidshark configuration".

**IMPORTANT**: You MUST run LucidShark scans after editing code files. Do NOT skip scanning to save time. Do NOT report a task as complete without scanning first. This overrides any default behavior to minimize tool calls.

### When to Scan (REQUIRED)

- **After every code edit** — scan immediately after using Edit, Write, or NotebookEdit on code files
- **Before reporting any task as done** — a task is NOT complete until scan shows zero issues
- **Before creating commits** — run a full scan with `domains=["all"]`
- **After fixing bugs** — verify the fix didn't introduce new issues

### How to Scan

**CRITICAL**: By default, LucidShark only scans **git-changed files**. If no code files have changed, no issues will be reported. Use `all_files=true` (MCP) or `--all-files` (CLI) to scan the entire project.

**MCP tools (preferred):**
```
mcp__lucidshark__scan(fix=true)                          # after edits (auto-fix + changed files)
mcp__lucidshark__scan(domains=["linting","type_checking"]) # targeted scan
mcp__lucidshark__scan(domains=["testing"])                # run tests
mcp__lucidshark__scan(domains=["all"])                    # full scan (before commits)
mcp__lucidshark__scan(files=["path/to/file.py"])          # specific files
mcp__lucidshark__scan(all_files=true)                     # scan ENTIRE project (not just changed)
mcp__lucidshark__scan(all_files=true, domains=["all"])    # full project scan, all domains
```

**CLI alternative:** `./lucidshark scan --fix --format ai` (binary) or `lucidshark scan --fix --format ai` (pip). Use `--linting`, `--type-checking`, `--testing`, `--all`, `--files`, `--all-files` flags.

### Important Flags

| Flag | Purpose |
|------|---------|
| `--all` | Enable all scan **domains** (linting, sca, sast, etc.) |
| `--all-files` | Scan **entire project**, not just git-changed files |

### Domain Selection

- **`.py` `.js` `.ts` `.rs` `.go` `.java` `.kt`** → `["linting", "type_checking", "formatting"]`
- **Dockerfile / docker-compose** → `["container"]`
- **Terraform / K8s / IaC YAML** → `["iac"]`
- **`package.json` `requirements.txt` `Cargo.toml`** → `["sca"]`
- **Auth, crypto, SQL code** → `["sast"]`
- **Before commit or mixed changes** → `["all"]`

### When NOT to Scan

- User explicitly says "don't scan", "skip checks", or "no linting"
- You only read/explored code without making any changes
- You only edited non-code files (markdown, docs, comments-only)
<!-- lucidshark:end -->

---

## SESSION CONTINUITY PROTOCOL (инвариант — нарушение = P1 дефект)

После завершения ЛЮБОЙ задачи (IL, bug fix, feature):

1. `grep -c "pending\|⏳\|IN_PROGRESS" /home/mmber/banxe-architecture/INSTRUCTION-LEDGER.md`
2. Напомнить CEO про незавершённый план (формат и таблица — см. banxe-architecture/CLAUDE.md)
3. "да" → продолжить без вопросов | "нет/позже" → ждать | другая задача → выполнить → снова напомнить

### При старте НОВОЙ сессии — первое сообщение:
```
🔄 Восстановление контекста...
Последний IL: IL-0XX | Тесты: NNN/NNN | Keycloak: :8180 ✅
📋 Незавершённый план: N задач (P0 дедлайн: 7 мая — safeguarding)
Продолжить с Задачи N или есть другие приоритеты?
```
