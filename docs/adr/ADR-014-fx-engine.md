# ADR-014: FX Engine Architecture

**Date:** 2026-04-20
**Status:** Accepted
**IL:** IL-FXE-01

## Context

Banxe requires FX rate provisioning, quote generation with 30-second TTL,
execution with best-execution compliance, and hedge position tracking.

## Decision

- Pydantic v2 models for FXRate/FXQuote/FXExecution (I-01)
- Quote TTL hard-capped at 30 seconds via pydantic validator
- Spread tiered: retail (50bps < £10k) / wholesale (30bps ≥ £10k) / institutional (15bps ≥ £100k)
- I-04: execution ≥ £10k → HITLProposal L4 (I-27), requires TREASURY_OPS
- BT-004 placeholder for live FX rate feed (Reuters/Bloomberg)
- ExecutionStore and HedgeStore append-only (I-24)
- Hedge alert at ≥£500k net exposure → HITLProposal (I-27)
- All amounts as Decimal, never float (I-22)
- UTC timestamps on all records (I-23)

## Consequences

- Sub-£10k FX executes automatically (L1 autonomy)
- Large FX requires human approval — FCA COBS 14.3 best execution documented
- PS22/9 reporting stub ready for regulatory activation
- Reject and requote always require HITL — irreversible commitments

## Alternatives Considered

- Reuters Elektron live feed: deferred to BT-004 — sandbox scope
- External hedge management system: InMemory stub sufficient for Sprint 34
