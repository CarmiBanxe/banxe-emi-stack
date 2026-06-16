# Operating Mode — Central <-> Factory

## Intensity Mode v2

### 1. Central (SHELL) — batched read-only diagnostics
Central read-only diagnostics MAY be emitted as a single artifact containing a
batch of atomic commands (multiple gh/git read-only calls chained). Every
command in the batch MUST be non-mutating. Batching reduces round-trips; it
never relaxes the read-only rule.

### 2. Factory (Claude Code) — full-sprint prompts
A Factory prompt MAY carry an ENTIRE sprint (a list of atomic tasks) as one
artifact, provided it includes explicit guards and an explicit file scope for
each task. Every task names its allowed files; any out-of-scope change MUST trip
a STOP-and-report guard before commit.

### 3. Preserved invariants
- Explicit venue tag on every artifact: -> SHELL (Central) or -> CLAUDE CODE (Factory). No tag means the artifact is not emitted.
- Best-solution principle: each reply is the single best actionable artifact for the current system state.
- No --admin and no bypass of branch protection, ever.
- Mutations only via Factory or the operator. Central never mutates project repos directly.
- Auto-continue: proceed through the plan without pausing to ask permission, within the above constraints.

### 4. Factory channel reliability (durable)
Headless `claude -p` in the current sandbox is flaky for combined
write+commit+push in a single run. Default such tasks to -> SHELL (Central)
operator blocks in MetaClaw with a scoped one-file guard. Do not widen the
allowlist to force it.

### 5. Merge invariant (unchanged)
A PR may be merged only when ALL of the following hold:
- state = OPEN
- base = main
- mergeable = MERGEABLE
- mergeStateStatus = CLEAN
