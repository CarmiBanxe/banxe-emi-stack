"""
services/safeguarding/internal/adapters/modulr_safeguarding_stub.py — Stub
implementation of SafeguardingExternalPort (Sprint S16.4 PREP).

PURPOSE
-------
Deterministic, in-memory stand-in for the live Modulr safeguarding-account
balance feed. Returns a hardcoded balance per (account_id, currency)
configured at construction time. Used by tests, local dev, and the
sandbox-tier reconciliation engine until the real adapter lands.

EXPLICIT NON-GOAL
-----------------
This file is a PREP stub:
  - No real HTTP calls.
  - No network access of any kind.
  - No env-var reads. No credential lookups. No secrets.
  - No live Modulr API integration here.

Sprint S20.1 will replace this stub with a real `ModulrSafeguardingAdapter`
that authenticates against Modulr's API, paginates accounts, normalises
currencies, and respects rate-limit/retry semantics per ADR-014/015.

TODO (Sprint S20.1 — real Modulr adapter):
  - Modulr API base URL + sandbox-vs-production toggle.
  - Request-auth scheme per Modulr signing requirements (token + HMAC).
  - Currency normalisation against the canonical FX feed.
  - Idempotent retry with exponential backoff.
  - Latency + error metric emission (per Sprint S16 observability).
  - Live-API smoke test gated by sandbox credentials.
  - Pagination across multiple safeguarding accounts per tenant.
  - Reconcile Modulr's account-id ↔ banxe customer-id mapping table.
  - Sandbox-vs-production read-only safety toggle (refuse writes in sandbox).
  - Structured-log redaction policy for response payloads.
"""

from __future__ import annotations

from decimal import Decimal


class ModulrSafeguardingStub:
    """Deterministic SafeguardingExternalPort stub for dev / test use.

    The stub holds a `(account_id, currency) -> Decimal` table provided at
    construction. Lookups return `Decimal("0.00")` for unknown keys. The
    stub never raises on a miss — the reconciliation engine treats a zero
    external balance against a non-zero internal balance as a break, which
    is the correct behaviour to exercise on the missing-data path.
    """

    def __init__(self, balances: dict[tuple[str, str], Decimal] | None = None) -> None:
        self._balances: dict[tuple[str, str], Decimal] = dict(balances or {})

    def fetch_safeguarding_balance(self, account_id: str, currency: str) -> Decimal:
        # I-01 invariant: amounts are Decimal, never float.
        return self._balances.get((account_id, currency), Decimal("0.00"))

    def set_balance(self, account_id: str, currency: str, balance: Decimal) -> None:
        """Test/dev helper — mutate the stub's in-memory table."""
        self._balances[(account_id, currency)] = balance
