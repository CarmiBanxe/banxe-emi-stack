# PAYBIS Wave A + B — what it does / does NOT do

> **Scope:** этот документ покрывает **Wave A** (this section) **и Wave B** (note ниже). Имя файла
> сохранено как `PAYBIS-WAVE-A.md`, чтобы ссылки из `LANDING-HANDOFF-MAIN.md` оставались валидными.

**Status:** Wave A (smallest safe slice). **Governance:** ADR-126 (NeuroNext retired, PAYBIS sole <!-- nosemgrep: banxe-no-neuronext-reintroduction -->
external crypto provider), ADR-108 (Paybis MiCA CASP, distribution/processor split, **non-custodial**),
ADR-114 (Travel-Rule on Paybis; go-live gate). **Plan:** `docs/paybis-dossier/PLAN-ROADMAP-SPRINTS-NEURONEXT-TO-PAYBIS.md`. <!-- nosemgrep: banxe-no-neuronext-reintroduction -->

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
- **No NeuroNext** — and a CI forward-guard (E9) is a separate sprint. <!-- nosemgrep: banxe-no-neuronext-reintroduction -->

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

---

# PAYBIS SANDBOX INSTALLATION STATUS

**Mode:** SANDBOX-only installation through the existing seam. **NOT live rollout.** No real creds/
secrets/endpoints/signature. **Approved-scope (legal):** PAYBIS usage limited to approved domains/
URLs/subdomains/ICT/environments/use-cases; sandbox base-URL + enablement are operator/PAYBIS-provided
(OPERATOR-GATE) — not invented.

## Installed (sandbox-safe)
- `services/ledger/production/paybis_sandbox.py` — `build_sandbox_config` (forces SANDBOX, **refuses
  PRODUCTION** → OPERATOR-GATE), `sandbox_guard` (fail-closed), `build_sandbox_transport` (returns the
  **fenced** transport — real sandbox HTTP needs SRC-06 endpoints), `PaybisSandboxWebhookSink`
  (in-memory **idempotent** intake, events **unverified** — signature fenced), `PAYBIS_ENV_CONTRACT`.
- `services/ledger/production/paybis_sandbox.env.example` — env-var contract (names only; **no values/
  secrets**): `PAYBIS_ENV=SANDBOX`, `PAYBIS_BASE_URL=` (OPERATOR-GATE), `PAYBIS_API_KEY=` (vault).
- Tests: +4 sandbox cases (config forces/refuses, guard+fenced transport, idempotent sink, env contract).
  **18 tests total, 100% coverage** across adapter + webhook + wave_b + sandbox.

## Completeness matrix (capability × status)
| Capability | Status | Evidence / note |
|---|---|---|
| provider health | **STRUCTURALLY INSTALLED BUT FENCED** | `adapter.health()` via transport; sandbox transport fenced (no live) |
| fee / quote estimate | **STRUCTURALLY INSTALLED BUT FENCED** | `get_fee_estimate` mock-routed; live fenced |
| order initiation | **STRUCTURALLY INSTALLED BUT FENCED** | `create_tx` → PENDING; live fenced; I-01 enforced |
| order status retrieval | **STRUCTURALLY INSTALLED BUT FENCED** | `get_order_status` deterministic (mock); live fenced |
| webhook intake | **STRUCTURALLY INSTALLED BUT FENCED** | `PaybisSandboxWebhookSink` parses structural payload; **unverified** |
| idempotency handling | **INSTALLED** | sink dedupe on `partnerOrderId`⊳`transactionId`; tested |
| sandbox env / config | **INSTALLED** | `build_sandbox_config` + env contract + `.env.example`; SANDBOX forced |
| error mapping / retriable transport | **INSTALLED** | `PaybisTransportError(retriable)` + `normalize_order_response` (malformed raises); tested |
| auth / signature handling | **BLOCKED BY MISSING LITERALS** | `auth_headers` + `verify_signature` fenced — scheme/**signature algorithm** НЕИЗВЕСТНО (SRC-06/08) |
| endpoint routing (sandbox routes) | **BLOCKED BY MISSING LITERALS** | `endpoint_for` fenced; sandbox base-URL OPERATOR-GATE (no guessed route) |
| live funds movement / Travel-Rule go-live | **OUT OF SCOPE** | non-custodial (ADR-108); ADR-114 gate = Wave C |
| wallet / balance via PAYBIS | **OUT OF SCOPE** | `OUT_OF_PAYBIS_SCOPE` (non-custodial, ADR-108) |

## OPERATOR-GATE blockers (sandbox → live-sandbox)
- **Sandbox base-URL + enablement** (`PAYBIS_BASE_URL`, API key in vault) — operator/PAYBIS provided, approved-scope only.
- **SRC-06** — endpoints, auth scheme, **signature algorithm**, request/response & webhook schemas (un-fences `endpoint_for`/`auth_headers`/`verify_signature` + a real sandbox transport).
- **SRC-07 + ADR-114** — Travel-Rule status + MLRO/HITL go-live gate (Wave C).
Until provided, the seam stays fenced and sandbox-only — no live calls, no funds, no secrets.

---

# PAYBIS SANDBOX — minimal-maximum provider install (runnable today)

**Thinnest insertion (ADR-102, reuses the seam):** `paybis_provider.py` adds a feature flag, a provider
selector, a runnable façade, a deterministic sandbox mock, and a smoke command. Microservice architecture
intact; NeuroNext-flow replacement compatible (PAYBIS sole provider, ADR-126). <!-- nosemgrep: banxe-no-neuronext-reintroduction -->

## Capability API (operator name ↔ façade)
`healthCheck()→health_check()` · `getQuote(input)→get_quote(blockchain, amount)` ·
`createOrder(input)→create_order(request)` · `getOrderStatus(id)→get_order_status(order_id)` ·
`handleWebhook(h,b)→handle_webhook(headers, body)`. *(snake_case kept for Python/ruff idiom; 1:1 map.)*

## WHAT IS REAL vs MOCKED vs FENCED
| Part | State |
|---|---|
| feature flag (`PAYBIS_ENABLED`) + selector (`select_paybis_provider`) | **REAL** |
| env contract / sandbox config (`PAYBIS_MODE`/`PAYBIS_ENV`, refuses PRODUCTION) | **REAL** |
| idempotency (webhook sink dedupe) + normalized error mapping | **REAL** |
| façade routing (health/quote/order/status/webhook) | **REAL** (delegates to adapter) |
| transport responses (quote/order/status values) | **MOCKED** (`SandboxMockPaybisTransport`, deterministic) |
| live HTTP transport / endpoints / auth headers | **FENCED** (SRC-06) |
| webhook signature verification | **FENCED** (algorithm НЕИЗВЕСТНО; events `verified:false`) |
| funds movement / Travel-Rule / wallet-balance | **OUT OF SCOPE** (non-custodial ADR-108; ADR-114 Wave C) |

## REQUIRED REAL LITERALS FROM PAYBIS (un-fence path)
1. **Sandbox base-URL + API credentials** (vault) — within approved domains/URLs/ICT/use-cases.
2. **SRC-06:** endpoint routes, auth scheme/headers, **webhook signature algorithm + signed fields**,
   request/response & webhook payload schemas, fee model.
3. **SRC-07 + ADR-114:** Travel-Rule status contract + MLRO/HITL go-live (Wave C).
> Until provided, transport/auth/signature stay fenced; the sandbox runs on the deterministic mock.

## HOW TO RUN THE SANDBOX SMOKE TEST
```bash
# from the banxe-emi-stack repo root (PYTHONPATH=repo root). Forces sandbox flags internally.
python -m services.ledger.production.paybis_provider
# → JSON: config_loaded, provider_selected, health, quote, order, order_status, webhook, ok:true
# or via pytest (the same flow asserted):
pytest tests/test_paybis_crypto_adapter.py -k "smoke or selection or provider" -q
```
Verifies: config loaded → provider selected → transport callable → mock path returns structured results.

---

# PAYBIS DI integration (api/deps.py — processing surface only)

**PAYBIS sandbox is DI-gated at `api/deps.py` only.** `get_crypto_application_service()` selects the
`processing` adapter via `_select_crypto_processing_adapter()`:
- `PAYBIS_ENABLED=true` **and** `PAYBIS_MODE=sandbox` → PAYBIS provider seam (`PaybisProcessingShim`
  over `select_paybis_provider()`), matching the `processing` port (`create_tx`/`get_fee_estimate`/`health`).
- else → `LegacyCryptoProcessingAdapter` (unchanged default).

**wallet and rpc stay legacy** (`LegacyCryptoWalletAdapter` / `LegacyCryptoRpcAdapter`) — **processing
is the only substituted surface** in this step (smallest blast radius). **Defensive fallback:** any
PAYBIS import/config/runtime failure logs and falls back to legacy (no invariant requires PAYBIS).
Production mode is refused (OPERATOR-GATE). FROZEN port + non-custodial boundary preserved through the shim.

**Next steps for deeper NeuroNext-flow replacement (separate, gated):** substitute wallet/rpc once a real <!-- nosemgrep: banxe-no-neuronext-reintroduction -->
sandbox transport exists (SRC-06); promote PAYBIS to default only after live enablement + ADR-114 go-live;
consolidate/retire legacy crypto adapters per PLAN E10 (PARKED until cutover).
