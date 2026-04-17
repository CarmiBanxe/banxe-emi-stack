# Batch Payments Agent Passport — BANXE AI BANK
# IL-BPP-01 | Phase 36 | banxe-emi-stack

## Agent Name

BatchAgent — Batch Payment Processing

## Version

1.0.0 (2026-04-17)

## IL Reference

IL-BPP-01

## Capabilities

- Create and manage payment batches across FPS/BACS/CHAPS/SEPA/SWIFT rails
- Parse Bacs Std18, SEPA pain.001 XML, Banxe CSV, SWIFT MT103 file formats
- Validate payment items: IBAN format, Decimal amounts, blocked jurisdictions (I-02)
- Dispatch validated items to payment gateway
- Reconcile dispatched items against gateway confirmations
- Enforce batch limits (£500k), daily limits (£2M), AML thresholds (£10k — I-04)
- Generate HITLProposal for all batch submissions (I-27)

## HITL Gates

| Gate | Threshold | Approver | Rule |
|------|-----------|----------|------|
| batch_submission | always | Compliance Officer | I-27, PSR 2017 |
| aml_item | item amount >= £10k | MLRO | I-04, MLR 2017 |
| daily_limit_exceeded | aggregate > £2M | Compliance Officer | I-04 |

## Autonomy Level

**L2** for batch creation, item addition, validation, reconciliation, status queries.
**L4** (HITL) for all batch submissions, AML threshold items.

## Invariants

| Invariant | Description |
|-----------|-------------|
| I-01 | All amounts as `Decimal` — never `float` |
| I-02 | Hard-block beneficiaries in RU/BY/IR/KP/CU/MM/AF/VE/SY |
| I-04 | EDD trigger at £10k per item |
| I-05 | API amounts as strings (DecimalString) |
| I-12 | SHA-256 file integrity hash |
| I-24 | Audit trail append-only |
| I-27 | Batch submission ALWAYS requires HITL |

## Protocol DI Ports

| Port | Production | Test |
|------|-----------|------|
| BatchPort | PostgresBatchStore | InMemoryBatchStore |
| BatchItemPort | PostgresBatchItemStore | InMemoryBatchItemStore |
| AuditPort | ClickHouseAuditStore | InMemoryAuditStore |
| PaymentGatewayPort | ModulrGatewayAdapter | InMemoryPaymentGateway |

## FCA / Regulatory References

- PSR 2017 (payment services — batch processing obligations)
- Bacs Direct Debit scheme rules (Std18 file format)
- SEPA Credit Transfer scheme (pain.001)
- MLR 2017 Reg.28 (sanctions screening on beneficiaries)
- EU AI Act Art.14 (human oversight for financial AI decisions)
