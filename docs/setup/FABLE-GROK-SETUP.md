# Fable Advisor + Grok CLI — setup status and operator handoff

Scope: wiring the `fable-advisor` Claude Code plugin (real, pre-existing local clone at
`external/fable-advisor`) and, optionally, the xAI Grok CLI it can route implementation work
to. See `docs/setup/fable-advisor-local-inspection.md` for the full plugin inspection.

## What was done automatically (read-only / additive / reversible only)

| Step | Artifact | Result |
|---|---|---|
| 1. Audit | `scripts/fable_grok_shell_audit.sh` | Created, executable, run. Confirms: `grok` not installed, no `GROK_*`/`XAI_API_KEY` env, `external/fable-advisor` plugin manifests present, `external/loop-engineering` present. |
| 2. Inspection | `docs/setup/fable-advisor-local-inspection.md` | Full read of all 3 agents (`fable-advisor`, `grok-implementer`, `codex-implementer`), the `orchestration` skill, and both plugin manifests. |
| 3. Installer download + inspect | `scripts/install_grok_safe.sh` | Created, executable, **run in inspect-only mode** (no `CONFIRM=yes`). Downloaded the real `https://x.ai/cli/install.sh` (SHA256 `0465d810453bbf18608ccae310fa79f4c59ae4a0538bd8a3a374ebce749be952`, 17003 bytes), read it in full, confirmed it: never uses `sudo`, installs only under `$HOME/.grok`, verifies the binary runs before installing, appends a PATH block to `~/.bashrc`/`~/.zshrc` (backs up the rc file first). No system change was made — the script stops after inspection unless `CONFIRM=yes` is set explicitly. |
| 4. Verification | `scripts/verify_grok_setup.sh` | Created, executable, run. Correctly reports current real state: 2/6 checks pass (plugin files present), 4/6 fail (grok not installed/authenticated) — matches the audit. |

Nothing on this machine was modified by these steps beyond creating the four scripts and two
docs listed above. No shell rc file, no `$HOME/.grok`, no Claude Code plugin registry entry was
touched.

## Why installing/authenticating Grok CLI is left as operator handoff

Two independent reasons, not one:

1. **It's genuinely a different kind of action** than everything else in this task. It fetches
   and executes a third-party vendor's installer, installs a new binary under `$HOME`, and
   edits shell rc files. `scripts/install_grok_safe.sh` makes this as safe as a `curl | bash`
   pattern can be (download → inspect → explicit `CONFIRM=yes` → then run), but the actual
   execution is still a real, system-level change that this session's own standing practice
   treats as something to pause on rather than silently perform.
2. **This specific tool has not been through this repo's Feature Evaluation Canon process** —
   the same structured evaluation that Kimi Code CLI / Hermes went through earlier in this
   engagement before being adopted. Grok CLI arrived here via the `fable-advisor` plugin's own
   requirements, not via that process. That's not disqualifying, but it means "install it" is
   a decision this handoff surfaces rather than one I make by proceeding quietly.

`grok login` is also an interactive OAuth-style flow — mechanically something only the operator
can complete (same category as `higgsfield auth login` encountered earlier this session).

### To actually install (operator-run)

```bash
# 1. Install (downloads + inspects again, then executes only with explicit confirm)
CONFIRM=yes bash scripts/install_grok_safe.sh

# 2. Authenticate (interactive — cannot be scripted)
grok login

# 3. Verify
bash scripts/verify_grok_setup.sh
```

## Fable-advisor plugin wiring (Claude Code slash commands — cannot be run via this session's Bash tool)

These are Claude Code CLI-level commands, not shell commands, so they were not and cannot be
executed as part of this task — they need to be run by the operator inside a Claude Code
session.

**Documented form (README, GitHub remote):**
```
claude plugin marketplace add DannyMac180/fable-advisor
claude plugin install fable-advisor@fable-advisor
```

**Local-path form (plausible, NOT verified against your Claude Code CLI version this session):**
```
claude plugin marketplace add external/fable-advisor
claude plugin install fable-advisor@fable-advisor
```
This is inferred from `external/fable-advisor/.claude-plugin/marketplace.json` declaring its
own plugin `source` as `"./"`, which is consistent with (but not proof of) Claude Code
supporting a local-directory marketplace add. Confirm with `claude plugin marketplace --help`
before relying on it — if it doesn't work, the GitHub remote form above is confirmed-documented
and will work identically since `external/fable-advisor`'s git remote points at the same repo.

**Important:** the plugin's `fable-advisor` (advisor) agent and `orchestration` skill work
today with zero further setup once the plugin is installed — they need no Grok CLI. Only the
`grok-implementer` agent's default lane needs the CLI installed+authenticated; absent that, it
reports `STATUS: unavailable` per its own design (never a silent Claude fallback).

## Summary for the operator

- Safe to do right now, no further confirmation needed: nothing — all safe/reversible steps
  are already done (scripts 1, 2, 4 above; step 3's script exists and was inspected-only).
- Needs your explicit action: run `claude plugin marketplace add …` / `claude plugin install …`
  inside Claude Code; optionally `CONFIRM=yes bash scripts/install_grok_safe.sh` then
  `grok login` if you want the Grok implementation lane (not required to use the advisor).
## Post-install audit — 2026-07-25T23:27:34Z (updated: auth now real)

**Ground truth, verified directly:**
- Grok CLI installed: `/home/mmber/.local/bin/grok`, version `grok 0.2.112 (9bbd559437)`.
- `~/.grok/auth.json` now **present** (1746 bytes, mode `600`, created 2026-07-26 01:07 local).
  `grok models` reports `You are logged in with grok.com.` — a durable auth source exists.
- `bash scripts/verify_grok_setup.sh` → **6 OK / 0 missing**.

**The `grok models` exit-code bug still exists as code** in `verify_grok_setup.sh` (exit `0`
regardless of auth state, as documented in the prior audit) — it is simply **no longer
load-bearing**, because the script's separate `auth.json`-presence check now also passes
independently, on its own merits, not because the buggy check was fixed. Fixing that check
remains a tracked follow-up (see ADR-043), not done here.

### Canonical durable auth sources (operator-only to create) — unchanged, now satisfied via `grok login`

| Source | Mechanism | Durability | Status |
|---|---|---|---|
| `~/.grok/auth.json` | `grok login` (interactive OIDC) | Persists on this machine across sessions | **Present** |
| `GROK_DEPLOYMENT_KEY` or `XAI_API_KEY` env var | Set via shell profile or secrets manager — never committed | As durable as the secret store | Not set (not needed — auth.json covers it) |

### Fable/Grok role split under sandbox/governed canon — unchanged

- **Fable 5 = advisor** (`fable-advisor` agent): read-only, commitment-boundary consult.
- **Grok 4.5 = executor** (`grok-implementer` agent): now has real, durable auth. Per ADR-043
  §2/§3, this makes the lane eligible for **sandbox/local use only** — staging and production
  remain gated exactly as ADR-043 defines, unaffected by this auth change.
- Neither role bypasses HITL levels (`agent-authority.md`), domain-separation boundaries
  (`compliance-boundaries.md`), or financial invariants (I-01, I-24, I-27). See ADR-043 for the
  formal activation and review conditions.
