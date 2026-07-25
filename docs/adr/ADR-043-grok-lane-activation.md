# ADR-043: Grok Implementation Lane — Activation Conditions

- Status: **DRAFT / Proposed** (§1 auth-proof condition SATISFIED for sandbox/local, 2026-07-25 — full ADR sign-off still pending)
- Date: 2026-07-25
- Deciders: (operator / MLRO / CTIO — sign-off pending)
- Related: `docs/setup/FABLE-GROK-SETUP.md`, `docs/setup/fable-advisor-local-inspection.md`,
  `.claude/rules/agent-authority.md`, `.claude/rules/compliance-boundaries.md`,
  `.claude/rules/80-ai-agents.md`

## Context

`external/fable-advisor` (local clone, `DannyMac180/fable-advisor` v3.1.0, MIT) ships a
`grok-implementer` subagent that drives the xAI Grok CLI as an implementation lane, and a
read-only `fable-advisor` agent (Fable 5) as a commitment-boundary advisor.

As of the original draft: Grok CLI was installed (`v0.2.112`) but had no auth of any kind. The
lane was inert by its own fail-loud design. This ADR defines the conditions for turning it on —
it does not itself activate anything.

## Decision (proposed)

### 1. Auth proof — explicit rule

**`grok models`'s exit code is never sufficient proof of authentication.** It returns `0`
regardless of auth state, printing `You are not authenticated.` to stdout on failure instead of
failing. Any "Grok lane ON" determination — automated or manual — must instead check for:
- a present `~/.grok/auth.json`, **or**
- a present `GROK_DEPLOYMENT_KEY` / `XAI_API_KEY`, **and**
- ideally, a real authenticated round-trip (e.g. an actual prompt/response), not a subcommand
  whose exit code doesn't encode auth failure.

`scripts/verify_grok_setup.sh`'s current auth check must be corrected to this standard before
it can be relied on as a gate (tracked as a follow-up, not part of this ADR).

**Update 2026-07-25T23:27:34Z:** `~/.grok/auth.json` is now present (verified: 1746 bytes,
mode `600`, `grok models` reports `You are logged in with grok.com.`). This satisfies the
auth-proof condition above for the **sandbox/local environment only** (§3). This does **not**
by itself satisfy §2 in full (quality-gate + domain-boundary conditions still apply per task)
and does **not** advance staging/production eligibility, which remain gated by their own
criteria in §3, unaffected by this auth change. `verify_grok_setup.sh`'s exit-code-based check
remains buggy as code and is tracked as an open follow-up below — it is not fixed by this
update, it is simply no longer the deciding signal now that `auth.json` presence passes
independently.

### 2. Grok lane is "ON" only when ALL of the following hold

- Real auth proof per §1 is satisfied.
- The invoking session runs under this repo's standard quality gate (Ruff, mypy, pytest ≥80%
  coverage, Semgrep) — every Grok-authored diff is verified exactly like any other diff, never
  merged on the subagent's self-report.
- The task is outside the AML/KYC/fraud/reconciliation/reporting domain boundaries in
  `compliance-boundaries.md`, unless it carries explicit sign-off under the relevant HITL gate.

### 3. Environment gating

| Environment | Grok lane allowed? |
|---|---|
| sandbox / local dev | Yes, once §1 auth proof is satisfied |
| staging | Only after a sandbox-use history threshold (count/duration set by operator) with a clean quality-gate record — no staging use on a first run |
| production (live ledger, live safeguarding data, `*prod*` config) | **Never direct.** Grok-authored changes reach production only via the standard PR path after human review — matches I-27 (AI proposes, human decides) |

### 4. Mandatory human review for Grok-generated diffs

- Every Grok-generated diff is treated as **L2 (Alert → Human)** at minimum, regardless of the
  autonomy level the task would otherwise carry — a human review step is mandatory in addition
  to the automated quality gate.
- Diffs touching `alembic/versions/**`, `services/*/api/**`, `services/*/contracts/**`,
  `infra/**`, `deploy/**`, or production config follow the existing "present plan, wait for YES"
  rule in the root `CLAUDE.md` unchanged — Grok gets no exception.
- Financial invariants (I-01, I-24, I-27) are enforced by the same quality gate that would
  reject a human-authored violation — no separate, weaker path for Grok output.

## Consequences

- Positive: cross-vendor implementation diversity for routine, well-specified work, with no
  weakening of existing gates.
- Negative: an environment-gating table to maintain; `verify_grok_setup.sh` must be fixed
  before §2's auth condition can be checked automatically rather than manually.
- Risk if this ADR is skipped: "Grok lane ON" has no formal definition, and a future change
  could wire it in without the environment/HITL gating above.

## Alternatives considered

- **Fold Grok into the compliance-swarm autonomy table** (`agent-authority.md`): rejected — it
  is a general-purpose code-writing tool, not a compliance-domain agent.
- **Ad hoc review, no ADR:** rejected — an inert lane today is exactly when activation
  conditions should be written down, not after the fact.

## Open questions (for sign-off)

- Exact sandbox-use threshold before staging eligibility (count, duration, or both)?
- Does `codex-implementer` get this same ADR, or a follow-up ADR-044?
- Who owns fixing the `verify_grok_setup.sh` auth-check bug, and on what timeline?
