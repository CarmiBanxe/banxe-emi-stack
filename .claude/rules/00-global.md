# Global Operating Rules — BANXE AI BANK
# Rule ID: 00-global | Load order: 00 (first)
# Created: 2026-04-11 | IL-SK-01

## Operating Posture

- **Conservative in regulated paths**: AML, KYC, ledger, reporting, auth, migrations, secrets
  — slow and correct beats fast and wrong.
- **Correctness > speed** in all financial code. Never rush a financial invariant to meet a deadline.

## Investigation Protocol

- **Read before edit**: always read the relevant file(s) before proposing or making changes.
- **Quote files in plans**: when presenting an implementation plan, cite exact file paths and
  line ranges that will be touched.
- **No inferred compliance**: never assume a regulatory requirement is satisfied; verify in code.
- **Facts vs assumptions**: clearly distinguish "I can see in the code that…" from "I believe…".

## Delivery Protocol

- **Reversible steps**: prefer additive changes (new function, new column, feature flag) before
  removing or replacing existing behaviour.
- **Small PR-sized patches**: one logical change per commit/PR. Do not bundle unrelated changes.
- **Stop before destructive**: for irreversible operations (DROP, DELETE, hard reset, secret rotation)
  pause and confirm with the engineer before proceeding.

## Evidence Protocol

- Compliance claims require evidence: file path, test name, migration file, or external reference.
- Do not mark a compliance item as done without pointing to the artefact that satisfies it.
- Distinguish regulatory sources: FCA PS, PRA SS, MLR, PSR, EU AI Act — name the source.

## Output Discipline

Every response that changes code MUST include:
1. **Scope** — what exactly changed (files, functions, DB objects)
2. **Affected files** — explicit list
3. **Change summary** — what behaviour changed and why
4. **Tests** — which tests cover the change (or why coverage is deferred)
5. **Risks** — any backward-compatibility, data, or compliance risks introduced
