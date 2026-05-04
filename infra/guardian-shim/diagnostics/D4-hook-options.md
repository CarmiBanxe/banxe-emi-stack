# GS-D4: Claude Code Hook Options — Guardian Shim Integration

**Snapshot date:** 2026-05-04
**Source:** .claude/settings.json (PreToolUse / PostToolUse / Stop hooks confirmed present)

---

## KEY FINDING: Strategy-S1 is viable — native `PreToolUse` Bash hook exists

`.claude/settings.json` already contains a working `hooks` structure:

```json
{
  "hooks": {
    "PreToolUse": [ { "matcher": "Edit|Write", "hooks": [...] } ],
    "PostToolUse": [ { "matcher": "Edit|Write|NotebookEdit", "hooks": [...] } ],
    "Stop": [ { "hooks": [...] } ]
  }
}
```

The `PostToolUse[1]` hook already reads `$TOOL_INPUT` for Bash:
```bash
FILE=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('file_path', d.get('command', '')))" ...)
```

This confirms:
- `$TOOL_INPUT` is a JSON string containing the tool input
- For Bash tool: `{"command": "<bash command string>"}`
- `PreToolUse` hooks CAN match `Bash` (Claude Code supports it)

---

## Option Comparison

### Strategy-S1 — Native `PreToolUse` Bash hook (RECOMMENDED)

**Activation:** Add to `.claude/settings.json`.hooks.PreToolUse:
```json
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "BASH_CMD=$(echo \"$TOOL_INPUT\" | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('command',''))\" 2>/dev/null || echo ''); printf '%s' \"$BASH_CMD\" | ~/.banxe/guardian-shim/claude-bash-shim.sh",
    "timeout": 10
  }]
}
```

**Pros:**
- Native integration — Claude Code calls hook before every Bash tool invocation
- `$TOOL_INPUT` provides exact command as Claude Code sees it (no interception needed)
- Supports verdict=fail → exit 1 → Claude Code blocks the Bash tool call
- No shell alias tricks, no wrapper scripts around `claude` binary
- Already working pattern in this repo (Edit|Write hook uses same mechanism)
- Settings survive Claude Code upgrades (stored in settings.json, not PATH tricks)

**Cons:**
- Hook only fires for Bash tool calls from within Claude Code sessions (not external bash)
- PreToolUse hook with exit non-zero blocks the tool call entirely (desired for enforce mode)
- If `claude` binary changes hook API — settings.json must be updated

**Verdict: BEST choice. Native, clean, no side effects.**

---

### Strategy-S2 — Shell alias wrapper `claude='~/.banxe/guardian-shim/claude-wrap.sh'`

**Activation:** `echo "alias claude='~/.banxe/guardian-shim/claude-wrap.sh'" >> ~/.bashrc`

**Mechanism:** Wrapper script intercepts the `claude` binary call, sets `BASH_ENV` to a
trap script, so every `bash` invocation sources the guardian shim.

**Pros:**
- Works even if Claude Code's hook API changes
- Can intercept shell functions, not just tool calls

**Cons:**
- BASH_ENV only affects non-interactive shells; Claude Code likely spawns bash directly
  with specific args (not as login/interactive shell) — BASH_ENV may not fire
- `trap DEBUG` on bash commands is unreliable and slow
- Breaks if claude binary path changes or nvm switches node version
- Complex, hard to debug, fragile

**Verdict: Fragile fallback. Only if S1 is impossible.**

---

### Strategy-S3 — PRE_COMMAND_HOOK env variable

**Check:** `claude --help` output does NOT show `PRE_COMMAND_HOOK` or `bash_wrapper` as
a supported env variable. The Claude Code binary is an ELF (not a shell script), so there's
no obvious env-based pre-command hook at the shell level.

**Pros:** If supported, cleanest env-based activation
**Cons:** NOT FOUND in `claude --help` or `claude config --help`. Not a viable option.

**Verdict: Not supported in this version of Claude Code.**

---

## Recommendation

**Use Strategy-S1.** The `PreToolUse` hook with `matcher: "Bash"` is:
1. Already confirmed working in this repo (PostToolUse uses same pattern)
2. Receives exact `$TOOL_INPUT` JSON with `command` field
3. Can block execution via exit code (PreToolUse hook exit ≠ 0 → tool blocked)
4. Stored in settings.json — persists across sessions

The shim command for S1:
```bash
BASH_CMD=$(echo "$TOOL_INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('command',''))" 2>/dev/null || echo ''); printf '%s' "$BASH_CMD" | ~/.banxe/guardian-shim/claude-bash-shim.sh
```

When verdict=fail and GUARDIAN_MODE=enforce: shim exits 1 → PreToolUse hook exits 1 →
Claude Code blocks the Bash tool call and reports reason to the session.
