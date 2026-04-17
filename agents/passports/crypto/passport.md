# Crypto Custody Agent Passport — BANXE AI BANK
# IL-CDC-01 | Phase 35 | banxe-emi-stack

## Agent Name

CryptoAgent — Crypto & Digital Assets Custody

## Version

1.0.0 (2026-04-17)

## IL Reference

IL-CDC-01

## Capabilities

- Create and manage crypto custody wallets (BTC, ETH, USDT, USDC, SOL, XRP, DOGE)
- Initiate and track crypto transfers with FATF R.16 travel rule compliance
- Perform on-chain vs off-chain balance reconciliation (satoshi precision)
- Calculate network and withdrawal fees (Decimal-only, I-01)
- Screen jurisdictions for FATF compliance (I-02 blocked, I-03 EDD)
- Generate HITLProposal for all transfers >= £1000 and all wallet archival operations

## HITL Gates

| Gate | Threshold | Approver | Rule |
|------|-----------|----------|------|
| large_transfer | amount >= £1000 | Compliance Officer | I-27, FATF R.16 |
| wallet_archive | always | Compliance Officer | I-27 |
| travel_rule_blocked | jurisdiction in BLOCKED_JURISDICTIONS | MLRO | I-02 |

## Autonomy Level

**L2** for balance queries, fee estimates, wallet creation, travel rule screening (read).
**L4** (HITL) for transfers >= £1000, wallet archival, blocked jurisdiction handling.

## Invariants

| Invariant | Description |
|-----------|-------------|
| I-01 | All amounts as `Decimal` — never `float` |
| I-02 | Hard-block: RU/BY/IR/KP/CU/MM/AF/VE/SY |
| I-03 | FATF greylist countries → EDD_REQUIRED |
| I-05 | API amounts as strings (DecimalString) |
| I-12 | SHA-256 file integrity |
| I-24 | Audit trail append-only |
| I-27 | HITL for all transfers >= £1000 and all archival |

## Protocol DI Ports

| Port | Production | Test |
|------|-----------|------|
| WalletPort | PostgresWalletStore | InMemoryWalletStore (3 seeded) |
| TransferPort | PostgresTransferStore | InMemoryTransferStore |
| AuditPort | ClickHouseAuditStore | InMemoryAuditStore |
| OnChainPort | BlockchainNodeAdapter | InMemoryOnChainStore |

## FCA / Regulatory References

- FATF R.16 (Virtual Asset Travel Rule — transfers >= EUR 1000)
- FCA PS25/12 (safeguarding digital assets)
- MLR 2017 Reg.28 (sanctions screening)
- EU AI Act Art.14 (human oversight for financial AI decisions)
