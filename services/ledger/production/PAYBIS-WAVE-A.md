# PAYBIS Wave A + B — what it does / does NOT do

> **Scope:** этот документ покрывает **Wave A** (this section) **и Wave B** (note ниже). Имя файла
> сохранено как `PAYBIS-WAVE-A.md`, чтобы ссылки из `LANDING-HANDOFF-MAIN.md` оставались валидными.

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

---

# PAYBIS Wave B — scaffolding note (on top of the Wave-A seam)

**Status:** Wave B = **mock-first + fenced live-readiness scaffolding** (NO live HTTP, NO secrets, NO funds, NO guessed signature). Builds on the Wave-A `PaybisTransportPort` without frozen-port drift.

## Wave B newly COVERS
- **Transport contract (minimal, compatible):** `PaybisTransportPort.get_order_status(order_id) → CryptoTransactionStatus` (deterministic order/status lookup; FROZEN status enum, **no new type**). Exposed on the adapter as an **extra helper** (`PaybisCryptoAdapter.get_order_status`) — **NOT** a `CryptoLedgerPort` method (frozen port unchanged). Default transport keeps it fenced.
- **Richer mock (`ConfigurableMockPaybisTransport`, tests):** healthy/unhealthy, fee responses, order-lifecycle, **retriable provider failure** (`PaybisTransportError(retriable=True)`), deterministic order→status table.
- **Live-readiness scaffolding (`paybis_wave_b.py`, pure + fenced):**
  - `build_order_request` — frozen request → provider-neutral structural dict (Decimal→str, I-01 guard; **no HTTP/secret/signature**).
  - `normalize_order_response` — raw mapping → FROZEN status; **raises `PAYBIS_MALFORMED_RESPONSE`** on not-a-dict / missing status.
  - `PaybisEndpoints.endpoint_for` — config-as-data routing; **fenced** while `base_url`/op-path unknown.
  - `auth_headers` — auth/header injection POINT; **fenced** (no secret read, no scheme guess).
- **Webhook edge cases:** snake_case keys + unknown status → safe `PENDING` (consistent fenced policy).
- **Tests:** 14 total, **100% coverage** on adapter + webhook + wave_b.

## Wave B still FENCED / blocked on literal PAYBIS spec
- **No live transport** — `FencedLivePaybisTransport` (incl. `get_order_status`) still raises `PaybisLiveFencedError`; `endpoint_for`/`auth_headers` fenced.
- **НЕИЗВЕСТНО (not invented):** endpoints, auth scheme, **signature algorithm**, exact request/response & webhook schemas, fee % — all blocked on **SRC-06** (+ SRC-07/08).
- **No funds movement, no secrets, no live HTTP, no Travel-Rule go-live** (ADR-114 gate, Wave C). FROZEN `CryptoLedgerPort`/`CryptoRpcPort` unchanged.
