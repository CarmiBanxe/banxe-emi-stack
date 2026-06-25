# PAYBIS Wave A — what it does / does NOT do

**Status:** Wave A (smallest safe slice). **Governance:** ADR-126 (NeuroNext retired, PAYBIS sole
external crypto provider), ADR-108 (Paybis MiCA CASP, distribution/processor split, **non-custodial**),
ADR-114 (Travel-Rule on Paybis; go-live gate). **Plan:** `docs/paybis-dossier/PLAN-ROADMAP-SPRINTS-NEURONEXT-TO-PAYBIS.md`.

## Files (Wave A)
- `services/ledger/production/paybis_crypto_adapter.py` — `PaybisCryptoAdapter` (FROZEN `CryptoLedgerPort`), injectable `PaybisTransportPort`, default `FencedLivePaybisTransport`, `PaybisConfig`, `PaybisEnv`, `map_order_status`.
- `services/ledger/production/paybis_webhook.py` — `PaybisWebhookEvent`, `parse_event`, `verify_signature` (fenced), idempotency key.
- `tests/test_paybis_crypto_adapter.py` — mock-first tests (100% module coverage).

## Wave A DOES
- Provide a **PAYBIS-only** adapter behind the **FROZEN** `CryptoLedgerPort` (port **unchanged**), alongside `MidazCryptoAdapter` — **no dual-provider logic**.
- Cover the smallest on/off-ramp slice through an **injectable mock transport**: `health`, `get_fee_estimate`, `create_tx` (initiate BuyCrypto/SellCrypto order → `PENDING`).
- Model the **webhook/event intake contract** (structural): parse known latin fields → `PaybisWebhookEvent`, map order/payment state → FROZEN `CryptoTransactionStatus`, expose an **idempotency key** (`partnerOrderId` ⊳ `transactionId`).
- Enforce invariants: **I-01** Decimal-only (float amount → `I01_DECIMAL`); positive-amount guard; **I-24** immutable FROZEN result dataclasses.
- Provide a **config-as-data** sandbox/prod switch with **no secrets** in code (only the env-var *name*; values read at runtime, never stored).

## Wave A does NOT (fenced / out of scope)
- **No live HTTP, no secrets, no funds movement, no PII flow.** The default transport raises `PaybisLiveFencedError`; live transport is Wave B (after **SRC-06** clean API spec).
- **No custody / wallet / balance via PAYBIS** — `get_balance` / `create_wallet_address` raise `OUT_OF_PAYBIS_SCOPE` (BANXE is non-custodial, ADR-108; wallet/balance are on-chain/Midaz).
- **No literal API guesses** — endpoints, auth, **signature algorithm**, request/response & webhook schemas, rate-limits/SLA, data-residency, fee % are **НЕИЗВЕСТНО** (SRC-06/07 pending). `verify_signature` raises rather than guessing.
- **No Travel-Rule go-live** — `travel_rule_engine` integration + ADR-114 gate (TR contract + MLRO) are Wave C.
- **No DI/container rewire, no consolidation** of existing crypto adapters (separate Wave-A sprints A-S3/A-S5).
- **No NeuroNext** — and a CI forward-guard (E9) is a separate sprint.

## Operator gates before Wave B/C
SRC-06 (API spec: endpoints/auth/signature/schemas/webhook), SRC-07 (TR-status schema), SRC-08 (MLRO owner + CASP T&C), full agreement `.docx` (approved domains/ICT/security/incident/audit). Until then live remains fenced.
