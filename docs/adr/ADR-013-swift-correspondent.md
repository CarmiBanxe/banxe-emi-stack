# ADR-013: SWIFT & Correspondent Banking Architecture

**Date:** 2026-04-20
**Status:** Accepted
**IL:** IL-SWF-01

## Context

Banxe requires SWIFT MT103/MT202 message generation for cross-border payments,
nostro reconciliation against correspondent banks, and gpi tracking.

## Decision

- Protocol DI for MessageStore/CorrespondentStore/NostroStore
- InMemory stubs with 3 seeded correspondents (Deutsche, Barclays, JPMorgan)
- BT-003 placeholder for live SWIFT Bureau connectivity
- MT103 field 70 remittance capped at 140 chars per SWIFT standard
- gpi UETR: UUID4, ACSP/ACCC/RJCT status enum per gpi SRD
- Nostro reconciliation tolerance: Decimal("0.01") — mismatch triggers HITL (I-27)
- HITL L4 required for all SEND/HOLD/REJECT decisions
- FATF greylist check on all counterparty registrations (I-03)
- All amounts as Decimal, never float (I-22)
- UTC timestamps on all records (I-23)
- NostroStore append-only (I-24)

## Consequences

- All live SWIFT operations require TREASURY_OPS human approval
- FATF greylist banks flagged at registration, EDD prefix added to remittance info
- NostroStore is append-only (I-24) — historical positions preserved
- Blocked jurisdictions (RU/BY/IR/KP/CU/MM/AF/VE/SY) excluded from lookups

## Alternatives Considered

- Direct SWIFT Bureau integration: deferred to BT-003 — sandbox scope
- External nostro reconciliation service: InMemory stub sufficient for Sprint 34
