# fable-advisor — local inspection

Source: `external/fable-advisor` (real, pre-existing local clone; git remote present).
Method: direct file reads, no assumptions. See `scripts/fable_grok_shell_audit.sh` for the
machine-checkable environment facts referenced below.

## Plugin manifest — found

- `external/fable-advisor/.claude-plugin/marketplace.json` — present.
  - `plugins[0].name`: `fable-advisor`
  - `plugins[0].source`: `"./"` (the plugin's source is the marketplace repo root itself)
  - owner: Dan McAteer (`github.com/DannyMac180`)
- `external/fable-advisor/.claude-plugin/plugin.json` — present.
  - `name`: `fable-advisor`, `version`: `3.1.0`, `license`: MIT
  - `homepage`: `https://github.com/DannyMac180/fable-advisor`

Both manifests parse as valid JSON and are internally consistent (plugin name matches the
marketplace entry name).

## Marketplace / plugin name / install path

- **Marketplace name:** `fable-advisor` (from `marketplace.json`, top-level `name`... actually
  the top-level object has no `name` key at marketplace level — the marketplace identity comes
  from the directory/repo itself; the *plugin* entry inside it is named `fable-advisor`).
- **Plugin name:** `fable-advisor`.
- **Documented install path (README.md, GitHub remote form):**
  ```
  claude plugin marketplace add DannyMac180/fable-advisor
  claude plugin install fable-advisor@fable-advisor
  ```
- **Local-path form:** not explicitly documented in the README (which only shows the
  `owner/repo` GitHub shorthand). Claude Code's `/plugin marketplace add` command is
  documented elsewhere to also accept a local filesystem path, and `marketplace.json`'s
  `source: "./"` is consistent with this repo being addable directly from its own directory
  (i.e. `external/fable-advisor` on this machine). **This local-path syntax has not been
  verified against the operator's installed Claude Code CLI version in this session** —
  treat the exact invocation as operator-confirmed, not asserted here.

## Agents shipped

| File | Model | Tools | Role |
|---|---|---|---|
| `agents/fable-advisor.md` | `fable` | Read, Grep, Glob | Read-only commitment-boundary advisor. Never implements. |
| `agents/grok-implementer.md` | `sonnet` (drives external `grok` CLI) | Bash, Read, Grep, Glob | Default implementation lane. Fails loudly (`STATUS: unavailable`) if `grok` CLI is missing/unauthenticated — never silently falls back to a Claude model. |
| `agents/codex-implementer.md` | `sonnet` (drives external `codex` CLI) | Bash, Read, Grep, Glob | Optional cross-vendor lane. Same fail-loud contract for the `codex` CLI. |

## Skill shipped

- `skills/orchestration/SKILL.md` — routing doctrine only (which lane, when, cost discipline,
  spec contract, verification requirements). No executable code; no install side effects.

## What each agent actually requires to function

- `fable-advisor` agent: **nothing external.** Runs today with Claude Code alone.
- `grok-implementer` agent: xAI **Grok CLI** on PATH + authenticated (`grok login`).
  Preflight is `command -v grok && grok --version && grok models`. **Not installed on this
  machine** (confirmed by `scripts/fable_grok_shell_audit.sh`: `grok CLI: NOT INSTALLED`).
- `codex-implementer` agent: OpenAI **Codex CLI** on PATH + authenticated (`codex login`).
  Not checked/installed on this machine (out of scope for this task — Grok lane only).

## Conclusion

The plugin itself (advisor agent + orchestration skill) is installable and usable **today**,
independent of whether the Grok CLI is ever installed — the README and the agent file both
state this explicitly ("Without it the agent reports `STATUS: unavailable` — it never silently
falls back to a Claude model"). Installing the plugin and installing/authenticating the Grok
CLI are two separable actions with very different risk profiles:

- Plugin install (`claude plugin marketplace add …` / `claude plugin install …`): Claude Code
  CLI slash-command action, no third-party binary execution, reversible (`claude plugin
  uninstall`).
- Grok CLI install: fetches and executes a third-party installer script from `x.ai`, installs
  a new binary, and requires a separate `grok login` auth flow. This is a materially different
  and larger action than adding the plugin, and is handled separately in
  `docs/setup/FABLE-GROK-SETUP.md`.
