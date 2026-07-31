# ADR-056: Herdr Control Room — Read-Only Observability Surface for Operator/Director

**Date:** 2026-07-31
**Status:** Accepted
**IL:** IL-OPS-01
**Author:** Moriel Carmi / Claude Code

---

## Context

The Director/operator needs a single observability surface over the whole EMI operation
(transaction monitoring, reconciliation, reporting, PSD2 plane, dashboards). The candidate
tool is **herdr 0.7.5** — an agent/terminal **multiplexer** installed host-level
(`~/.local/bin/herdr`), running multiplexer-only (socket API OFF, plugins OFF; provenance
IL-1121, banxe-architecture PR #1175).

A terminal multiplexer renders panes, tracks process liveness, and survives detach/reattach.
It is **NOT an orchestrator**: it has no transaction model, no authorization model, no
idempotency, no ledger attribution. Placing it into the regulated instruction path would be
a category error and would create a second, non-canonical orchestrator — rejected by
architecture-side canon (ADR-102 dedup, ADR-103 server-only, ADR-164 Herdr revisit-B:
multiplexer-only) and by this stack's invariants (I-24 append-only audit, I-27 HITL).

The operator ratified **Option B** (2026-07-31, Rule 11): adopt a Control-Room observability
layer in banxe-emi-stack, gated by this ADR + INVARIANTS review, multiplexer-only.

## Decision

**Herdr = read-only Control Room for the operator/Director. It NEVER originates, modifies,
approves, or relays a client instruction. Multiplexer-only: socket API OFF, plugins OFF.**

### Technical boundary (MUST)

The Control-Room session runs under a **dedicated non-privileged OS user**:

- no `docker` group membership;
- no engine/DB credentials in its environment;
- no write-scoped tokens;
- **no midaz access** (midaz is a foreign core-banking DB — untouchable, ADR-003).

The boundary is technical, not just policy: even a misused pane physically lacks a write path.

### Panes MAY (read-only)

- tail read-only service logs: transaction-monitor, recon, reporting, psd2/mock-aspsp;
- GET health/status endpoints; watchdog output;
- view grafana / superset dashboards.

### Panes MAY NOT

- run `docker compose up/down/exec/restart` or any container mutation;
- call any POST/PUT/DELETE on engine or payment APIs;
- hold DB credentials or query postgres / clickhouse / redis / **midaz**;
- submit, approve, cancel, or relay client instructions;
- touch n8n workflows.

Herdr itself stays a host-level operator tool — never a compose service of the stack; the
socket-API subcommands (`herdr api|pane|tab|agent|workspace|...`) and plugins/integrations
remain OFF and out of scope.

## Consequences

- **Segregation of duties preserved:** all mutations happen OUTSIDE the Control Room through
  existing gated runbooks and are attributed there (append-only ledger, ADR-059-A discipline);
  keystrokes in a pane never become an unaudited side channel into payment execution.
- **Regulatory:** instruction execution stays traceable and reconstructable for the
  supervisor; the Control Room adds visibility without adding an execution surface.
- Operator gains one persistent surface (detach/reattach over SSH) for the whole operation;
  see `docs/runbooks/CONTROL-ROOM.md` for layout and procedures.
- Future proposals to enable herdr's socket API, plugins, or any write path must repeal this
  ADR explicitly (new ADR + operator ratification), not extend it.

## Cross-references

- banxe-architecture: ADR-164 (Herdr revisit-B, multiplexer-only), ADR-102 (dedup / no second
  orchestrator), ADR-103 (server-only execution path), ADR-059-A (append-only ledger).
- banxe-emi-stack: `INVARIANTS.md` (INV-OPS-01 — added with this ADR), ADR-003 (midaz
  core-banking boundary), I-24, I-27.
- Runbook: `docs/runbooks/CONTROL-ROOM.md`.
