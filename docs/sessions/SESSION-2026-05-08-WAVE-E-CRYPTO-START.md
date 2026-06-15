# SESSION-2026-05-08 — Wave E: CRYPTO/LEDGER Import Start

**Date:** 2026-05-08  
**Phase:** Phase 4 — Wave E (final wave)  
**Branch:** `sprint5/wave-e-crypto-import-2026-05-08`  
**Upstream PRs merged:** Wave D #85 (SumSub) + #86 (BKYC) + #87 (BinanceKYC) — all closed

---

## Stack Confirmed

| Repo | Language | Framework | ORM | Queue | Amounts |
|------|----------|-----------|-----|-------|---------|
| `crypto-processing-backend` | TypeScript | NestJS | TypeORM | Bull/RabbitMQ | BigNumber.js |
| `crypto-api-rpc` | TypeScript | NestJS | — | RabbitMQ | BigNumber.js |
| `crypto-api-wallet` | TypeScript | NestJS | TypeORM | RabbitMQ | BigNumber.js |

**Blockchain clients** (all per `crypto-api-rpc`): BTC, ETH, TRX, XRP, DOT, EOS  
**Extraction:** `evo1:/tmp/banxe-rar-stage/wave-e` — 509 files, 1.4 GB (read-only staging, NOT in repo)  
**Verified paths:** `docs/inventories/WAVE-E-CRYPTO-PATHS.txt` — 661 source paths

---

## Top-15 Entry Points

| Rank | Score | Path (relative to staging) | Verdict | Port Target |
|------|-------|---------------------------|---------|-------------|
| 1 | 297 | `crypto-api-wallet/src/wallet/btc.service.ts` | REWRITE-7 primary | `CryptoLedgerPort.get_balance()` / `create_wallet_address()` |
| 2 | 195 | `crypto-api-wallet/src/wallet/eth.service.ts` | REWRITE-7 chain variant | `CryptoLedgerPort.get_balance()` |
| 3 | 176 | `crypto-api-wallet/src/wallet/db/address.service.ts` | REWRITE-7 support | `CryptoLedgerPort` address index |
| 4 | 144 | `crypto-api-wallet/src/wallet/xrp.service.ts` | REWRITE-7 chain variant | `CryptoLedgerPort.get_balance()` |
| 5 | 125 | `crypto-api-wallet/src/api/controllers/controller-btc.service.ts` | REWRITE-7 facade | drop (NestJS controller) |
| 6 | 122 | `crypto-api-wallet/src/wallet/dot.service.ts` | REWRITE-7 chain variant | `CryptoLedgerPort.get_balance()` |
| 7 | 104 | `crypto-api-wallet/src/wallet/db/transaction.service.ts` | REWRITE-8 candidate | `CryptoLedgerPort.list_transactions()` |
| 8 | 96 | `crypto-api-wallet/src/wallet/eos.service.ts` | REWRITE-7 chain variant | `CryptoLedgerPort.get_balance()` |
| 9 | 96 | `crypto-api-rpc/src/blockchains/trx.service.ts` | REWRITE-9 candidate | `CryptoRpcPort.get_block()` / `broadcast_tx()` |
| 10 | 94 | `crypto-api-wallet/src/api/controllers/controller-eth.service.ts` | REWRITE-7 facade | drop (NestJS controller) |
| 11 | 85 | `crypto-api-wallet/src/api/api.service.ts` | REWRITE-7 orchestrator | `CryptoLedgerPort` |
| 12 | 84 | `crypto-api-rpc/src/blockchains/xrp.service.ts` | REWRITE-9 candidate | `CryptoRpcPort` |
| 13 | 78 | `crypto-api-wallet/src/rpc/rpc.service.ts` | REWRITE-9 primary | `CryptoRpcPort.broadcast_tx()` |
| 14 | 73 | `crypto-api-wallet/src/wallet/db/account.service.ts` | REWRITE-7 support | `CryptoLedgerPort` account index |
| 15 | 71 | `crypto-processing-backend/src/queues-consumers/services/transactions/transaction-queues-fee-consumer.service.ts` | REWRITE-8 primary | `CryptoLedgerPort.create_tx()` |

---

## Top-3 REWRITE Candidates

### REWRITE-7 — `LegacyCryptoWalletAdapter` → `CryptoLedgerPort`
**Source:** `crypto-api-wallet/src/wallet/*.service.ts` (btc/eth/xrp/dot/eos)  
**Source LOC:** ~1 500 TS across 6 chain services  
**Business logic:** wallet address derivation, balance aggregation, UTXO selection (`coinselect`)  
**Drop:** TypeORM entities, NestJS `@Injectable` / `@InjectRepository`, KeysService (key derivation), RpcService (direct node calls), `BigNumber` → `Decimal` (I-01)  
**Port methods:** `get_balance(wallet_id, currency)`, `create_wallet_address(customer_id, blockchain)`, `list_transactions(wallet_id)`

### REWRITE-8 — `LegacyCryptoProcessingAdapter` → `CryptoLedgerPort`
**Source:** `crypto-processing-backend/src/` — invoices, TX queue consumer, fee transfers  
**Source LOC:** ~450 TS in `transaction-queues-fee-consumer.service.ts` + `TransactionsService`  
**Business logic:** invoice fee transfer, idempotent TX creation, internal TX ID generation  
**Drop:** Bull `@Processor` / `@Process`, TypeORM `Connection`/`EntityManager`, `BigNumber`, RabbitMQ producers  
**Port methods:** `create_tx(request)`, `get_tx(tx_id)`, `get_fee_estimate(blockchain, amount)`

### REWRITE-9 — `LegacyCryptoRpcAdapter` → `CryptoRpcPort`
**Source:** `crypto-api-rpc/src/blockchains/*.service.ts` (btc/eth/trx/xrp/dot/eos)  
**Source LOC:** ~600 TS across 6 blockchain services  
**Business logic:** block fetching, TX broadcasting, UTXO query, fee estimation per chain  
**Drop:** NestJS DI, RabbitMQ notification service, direct `web3`/`ethers`/`bitcoinjs` HTTP clients  
**Port methods:** `broadcast_tx(signed_tx, blockchain)`, `get_block(block_hash, blockchain)`, `estimate_fee(blockchain, priority)`

---

## Adapter Seam Plan

```
services/ledger/legacy/           ← NEW (Wave E)
├── __init__.py                   ← anchor stub (created this session)
├── legacy_crypto_wallet_adapter.py    ← REWRITE-7 (next)
├── legacy_crypto_processing_adapter.py ← REWRITE-8
└── legacy_crypto_rpc_adapter.py       ← REWRITE-9
```

New Protocol required: `services/ledger/crypto_ledger_port.py` (ADR-031 Proposed)  
New Protocol required: `services/ledger/crypto_rpc_port.py` (ADR-031 Proposed)

---

## ADR-031 Status

**REQUIRED: YES**

- `services/ledger/ledger_port.py` covers only GL double-entry bookkeeping (accounts, journal entries, balances in GBP/EUR/USD).
- No `CryptoLedgerPort`, no `CryptoRpcPort`, no crypto-specific wallet or blockchain port exists.
- ADR-031 (Proposed) must define:
  - `CryptoLedgerPort` — wallet address management + balance + TX creation
  - `CryptoRpcPort` — blockchain node connectivity (broadcast, blocks, fees)
  - Amount handling: `Decimal` only (I-01), `str` for blockchain addresses, `str` for TX hashes
  - Supported blockchains enum: BTC, ETH, TRX, XRP, DOT, EOS

---

## Frozen List (DO NOT TOUCH)

| Path | Frozen since | Notes |
|------|-------------|-------|
| `services/auth/*` | Wave A+B | Auth ports + TOTP adapter |
| `services/compliance/legacy/legacy_jwt_strategy_adapter.py` | Wave A | JWT |
| `services/compliance/legacy/legacy_role_guard_adapter.py` | Wave A | RBAC |
| `services/compliance/legacy/legacy_totp_adapter.py` | Wave B | TOTP |
| `services/compliance/legacy/legacy_sumsub_adapter.py` | Wave D #85 | KYC |
| `services/compliance/legacy/legacy_bkyc_adapter.py` | Wave D #86 | KYC |
| `services/compliance/legacy/legacy_binancekyc_adapter.py` | Wave D #87 | KYC |
| `services/payment/*` | Wave C | Payment ports |
| `services/ledger/ledger_port.py` | IL-FIN-01 | GL LedgerPort |
| `services/ledger/midaz_adapter.py` | IL-FIN-01 | Midaz GL adapter |

---

## Canon References

- ADR-015 — Hexagonal architecture + Protocol DI pattern
- ADR-025 §15-16 — REWRITE drop rules (transport, DI, ORM, queue)
- ADR-029 — Wave sequencing + frozen guard
- ADR-030 — (check existence) Wave D KYC seam
- ADR-031 — **PROPOSED** — CryptoLedgerPort + CryptoRpcPort (to be created in REWRITE-7)
- AUTH_IMPORT_ORDER — import ordering convention

---

## Next Step

**REWRITE-7**: `LegacyCryptoWalletAdapter` — Python in-memory adapter behind `CryptoLedgerPort`  
Source: `crypto-api-wallet/src/wallet/*.service.ts` (btc/eth/xrp/dot/eos — ~1 500 TS LOC)  
Staging: `evo1:/tmp/banxe-rar-stage/wave-e/crypto-api/crypto-api-wallet/src/`  
Target: `services/ledger/legacy/legacy_crypto_wallet_adapter.py`  
Prerequisite: create `services/ledger/crypto_ledger_port.py` (ADR-031)
