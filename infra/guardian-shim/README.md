# Guardian Bash Shim — Claude Code Pre-Command Enforcement
# ADR-024 | I-36 | banxe-emi-stack

## Overview

`claude-bash-shim.sh` intercepts every Bash tool call from Claude Code and sends it to
BANXE Guardian `/audit` for policy evaluation before execution. Verdict determines action:

| Verdict | AUDIT mode | ENFORCE mode |
|---------|-----------|-------------|
| pass    | proceed   | proceed     |
| warn    | proceed + log | proceed + log |
| unknown | proceed + log | proceed + log |
| fail    | proceed + log (non-blocking) | **BLOCK** (exit 1) |

Guardian unreachable: fail-open in AUDIT, fail-closed in ENFORCE.

## Architecture

```
Claude Code Bash tool
      │
      ▼ PreToolUse hook ($TOOL_INPUT → command field)
claude-bash-shim.sh
      │  mask secrets (sed)
      │  POST /audit {subject_type, subject_id, scope, prompt, actor, dry_run:false}
      ▼
Guardian factory :8195 (http://192.168.0.72:8195)
      │
      ▼ verdict {result, summary, reasons, sources}
claude-bash-shim.sh
      │  log to ~/.claude/guardian-shim/audit.log
      ▼
exit 0 (pass/warn/unknown/audit-fail) OR exit 1 (enforce-fail)
      │
      ▼ Claude Code: proceed OR block tool call
```

## Env Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GUARDIAN_BASE_URL` | `http://192.168.0.72:8195` | Guardian factory endpoint (IP-form, WSL2 DNS) |
| `GUARDIAN_MODE` | `audit` | `audit` / `enforce` / `off` |
| `GUARDIAN_FAIL_MODE` | `open` (audit) / `closed` (enforce) | Behaviour when Guardian unreachable |
| `GUARDIAN_TIMEOUT_S` | `5` | HTTP timeout in seconds |
| `GUARDIAN_SCOPE` | `claude.bash` | Guardian scope identifier |
| `GUARDIAN_SUBJECT_TYPE` | `claude-code-session` | Guardian subject_type |
| `GUARDIAN_SUBJECT_ID` | `hostname-$$` | Session identifier |
| `GUARDIAN_ACTOR` | `$USER` | Operator identity |

## Activation Strategies

### Strategy-S1 — Native Claude Code `PreToolUse` hook (ACTIVE)

Entry in `.claude/settings.json → hooks.PreToolUse`:
```json
{
  "matcher": "Bash",
  "hooks": [{
    "type": "command",
    "command": "BASH_CMD=$(echo \"$TOOL_INPUT\" | python3 -c \"import sys,json; d=json.load(sys.stdin); print(d.get('command',''))\" 2>/dev/null || echo ''); printf '%s' \"$BASH_CMD\" | $HOME/.banxe/guardian-shim/claude-bash-shim.sh",
    "timeout": 10
  }]
}
```
Hook fires before every Bash tool call. `$TOOL_INPUT` is JSON with `command` field.
Exit 1 from hook → Claude Code blocks the tool call entirely.

### Strategy-S2 — Shell alias wrapper (fallback only)

```bash
alias claude='~/.banxe/guardian-shim/claude-wrap.sh'
```
See `scripts/claude-wrap.sh`. Fragile; only if S1 unavailable.

### Strategy-S3 — PRE_COMMAND_HOOK env

Not supported by current Claude Code binary. Eliminated.

## Installation

```bash
# 1. Copy shim to stable path
mkdir -p ~/.banxe/guardian-shim
cp infra/guardian-shim/scripts/claude-bash-shim.sh ~/.banxe/guardian-shim/
chmod +x ~/.banxe/guardian-shim/claude-bash-shim.sh
cp infra/guardian-shim/scripts/claude-bash-shim.env ~/.banxe/guardian-shim/

# 2. Source env from ~/.bashrc
cat infra/guardian-shim/scripts/claude-bash-shim.env >> ~/.bashrc

# 3. (S1 only) Ensure .claude/settings.json PreToolUse Bash hook is wired
#    (already done in this PR — settings.json updated)

# 4. Fix hostname resolution (optional; alternative to IP in GUARDIAN_BASE_URL)
# sudo sh -c 'echo "192.168.0.72 evo1" >> /etc/hosts'
```

## Switching Modes

```bash
# Audit only (default — log, non-blocking)
export GUARDIAN_MODE=audit

# Enforce (block on verdict=fail)
export GUARDIAN_MODE=enforce

# Emergency bypass (logged)
export GUARDIAN_MODE=off
```

## Logs

Local: `~/.claude/guardian-shim/audit.log` (JSON-lines, one per bash call)

```json
{"ts":"2026-05-04T10:30:00Z","mode":"audit","result":"unknown","summary":"...","reasons":[],"request_id":"..."}
{"ts":"2026-05-04T10:30:01Z","mode":"audit","action":"unreachable","fail_mode":"open"}
{"ts":"2026-05-04T10:30:02Z","mode":"off","action":"bypass"}
```

Canonical: Guardian → ClickHouse (FCA-grade, 12-month retention per G-GUARD-03).

## Running Tests

```bash
bash infra/guardian-shim/tests/test-shim.sh
```

## Rollout

| Date | Action |
|------|--------|
| T+0 (2026-05-04) | Merged, AUDIT default |
| T+7 (2026-05-11) | Switch to ENFORCE for compliance repos (G-GUARD-02) |
| T+14 (2026-05-18) | ENFORCE everywhere (G-GUARD-04) |

## Activation log — 2026-05-04

**Operator:** Moriel Carmi | **Session:** GS-A live activation | **Mode:** audit (default)

### GS-A0 — main pull
```
Updating 57797b7..c6685c5 Fast-forward
  .claude/settings.json + infra/guardian-shim/** (PR #48 merged)
```

### GS-A1 — shim installed
```
~/.banxe/guardian-shim/claude-bash-shim.sh  (chmod +x)
~/.banxe/guardian-shim/claude-bash-shim.env
```

### GS-A2 — ~/.bashrc env block added
```bash
export GUARDIAN_BASE_URL="http://192.168.0.72:8195"   # WSL2 IP (DNS gap)
export GUARDIAN_MODE="audit"
export GUARDIAN_FAIL_MODE="open"
export GUARDIAN_TIMEOUT_S="5"
export GUARDIAN_SCOPE="claude.bash"
export GUARDIAN_SUBJECT_TYPE="claude-code-session"
```

### GS-A4 — smoke #1 (safe command: ls -la /tmp)
```
verdict: unknown | summary: "unknown scope 'claude.bash' — expected one of: factory, project"
EXIT=0  ✅ (audit non-blocking)
```
Audit log entry:
```json
{"ts":"2026-05-04T11:44:26Z","mode":"audit","result":"unknown","summary":"unknown scope 'claude.bash'...","reasons":[],"request_id":"..."}
```

### GS-A5 — smoke #2 (destructive: rm -rf /)
```
verdict: unknown | EXIT=0  ✅ (audit non-blocking)
```
**Gap G-GUARD-01 confirmed:** scope `claude.bash` has no rules in Guardian — both safe and
destructive commands receive `unknown`. Rule coverage target: ≥90% by 2026-05-11.

### GS-A6 — smoke #3 (unreachable Guardian)
```
audit  + fail-open:   EXIT=0  ✅  (proceeds: "Guardian unreachable; fail-open")
enforce + fail-closed: EXIT=2  ✅  (blocks:   "Guardian unreachable; fail-closed")
```

### Summary
| Step | Result |
|------|--------|
| Shim installed to `~/.banxe/guardian-shim/` | ✅ |
| `~/.bashrc` env block added | ✅ |
| Strategy-S1 `PreToolUse` Bash hook active | ✅ (PR #48) |
| Live verdict received from Guardian :8195 | ✅ unknown (G-GUARD-01 gap) |
| Fail-open (audit unreachable) | ✅ EXIT=0 |
| Fail-closed (enforce unreachable) | ✅ EXIT=2 |

---

## Enforcement activation log — 2026-05-05 11:00 CEST (V-01 closure)

**State change:** `GUARDIAN_MODE=enforce`, `GUARDIAN_FAIL_MODE=closed` (was: audit/open).

**Trigger:** MetaClaw `d122a61 feat(guardian): add scope claude.bash with ADR-025 canon ruleset [V-01]` deployed to evo1 `/data/banxe/guardian/`. Both Guardian units restarted via systemd:

- `banxe-guardian-factory.service` — PID 203936 :8195
- `banxe-guardian-project.service` — PID 203939 :8196

**Smoke results (interactive bash with .bashrc-sourced enforce env):**

| Prompt | Verdict | Shim exit |
|---|---|---|
| `ls -la /tmp` | pass (4/4 OK) | 0 |
| `cat compliance/cases/case-001/notes.txt` | fail — CB1-deny-path | 1 |
| `cat /home/user/.env` | fail — CB1 + CB2 (.env + secret-leak) | 1 |
| `sudo rm -rf /` | fail — CB4-dangerous-cmd | 1 |

**Files changed in this PR:**

- `infra/guardian-shim/scripts/claude-bash-shim.env` — defaults flipped audit→enforce, open→closed.

**Operator action required for new sessions:** open a fresh interactive shell so `~/.bashrc` sources the updated env. Existing live shells continue with their previously sourced (audit) env until restart.

**Closes:** G-GUARD-02 (Switch banxe-emi-stack + banxe-architecture to GUARDIAN_MODE=enforce). V-01 in HANDOFF-2026-05-04.

