"""PAYBIS SANDBOX installation scaffolding — sandbox-only, fenced where literals НЕИЗВЕСТНО.

NOT live rollout. No real creds/secrets/endpoints/signature. Installs the SANDBOX-safe pieces
AROUND the existing seam (`PaybisCryptoAdapter` / `PaybisTransportPort` / `paybis_webhook`):

  - **ENV VAR CONTRACT** (names only — values live in a vault / PAYBIS enablement, never in repo).
  - `build_sandbox_config` — forces env = SANDBOX; **refuses PRODUCTION** (OPERATOR-GATE: live not
    enabled in a sandbox install).
  - `sandbox_guard` — asserts a config is sandbox before any wiring (fail-closed).
  - `build_sandbox_transport` — returns the FENCED transport: a real sandbox HTTP transport needs
    endpoints/auth (SRC-06) → OPERATOR-GATE; until then **no live calls**.
  - `PaybisSandboxWebhookSink` — in-memory idempotent webhook intake for sandbox testing. Events are
    recorded **unverified** (`verify_signature` stays fenced — НЕИЗВЕСТНО algorithm; sandbox never
    asserts a verified signature).

**Approved-scope (legal):** PAYBIS usage is limited to approved domains/URLs/subdomains/ICT systems/
environments/use-cases; testing/activation depends on PAYBIS-provided enablement. The sandbox
base-URL + creds are OPERATOR-GATE (operator/PAYBIS provided) — NOT invented here.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.ledger.crypto_ledger_port import CryptoLedgerError
from services.ledger.production.paybis_crypto_adapter import (
    FencedLivePaybisTransport,
    PaybisConfig,
    PaybisEnv,
    PaybisTransportPort,
)
from services.ledger.production.paybis_webhook import PaybisWebhookEvent, parse_event

# ── ENV VAR CONTRACT (config-as-data; names only, no values) ───────────────────────
# Documents what the operator must provide via vault / PAYBIS enablement. The VALUES are
# never stored in the repo (I-SEC). Empty/unprovided literals stay OPERATOR-GATE / fenced.
PAYBIS_ENV_CONTRACT: dict[str, str] = {
    "PAYBIS_ENV": "SANDBOX | PRODUCTION — a sandbox install expects/forces SANDBOX",
    "PAYBIS_BASE_URL": "sandbox base URL — OPERATOR-GATE (PAYBIS enablement, approved-scope only); empty until provided",
    "PAYBIS_API_KEY": "NAME of the env var holding the API key; the VALUE lives in a vault, never in repo",
}


class PaybisSandboxError(CryptoLedgerError):
    """Raised when a sandbox-install guard is violated (e.g. a non-SANDBOX env is requested)."""


def build_sandbox_config() -> PaybisConfig:
    """Build a SANDBOX PaybisConfig from env. Refuses a PRODUCTION env — a sandbox installation
    pass must NOT enable live (OPERATOR-GATE). base_url stays whatever the operator provided
    (empty → endpoint routing remains fenced)."""
    cfg = PaybisConfig.from_env()
    sandbox_guard(cfg)
    return cfg


def sandbox_guard(config: PaybisConfig) -> None:
    """Fail-closed: assert the config is SANDBOX before any sandbox wiring is constructed."""
    if config.env is not PaybisEnv.SANDBOX:
        raise PaybisSandboxError(
            "sandbox install refuses a non-SANDBOX env "
            "(OPERATOR-GATE: production/live not enabled in a sandbox pass)",
            code="PAYBIS_SANDBOX_ONLY",
        )


def build_sandbox_transport(config: PaybisConfig | None = None) -> PaybisTransportPort:
    """Sandbox transport. A real sandbox HTTP transport needs endpoints/auth (SRC-06) →
    OPERATOR-GATE; until provided this returns the FENCED transport (no live calls). Tests inject
    a mock instead."""
    cfg = config or build_sandbox_config()
    sandbox_guard(cfg)
    return FencedLivePaybisTransport(cfg)


@dataclass
class PaybisSandboxWebhookSink:
    """In-memory idempotent webhook intake for SANDBOX testing. Parses the payload, dedupes on the
    idempotency key, and records the event. Signature is NOT verified (sandbox; `verify_signature`
    fenced) — events carry no verified-signature claim."""

    _seen: set[str] = field(default_factory=set)
    events: list[PaybisWebhookEvent] = field(default_factory=list)
    duplicates: int = 0

    def intake(self, payload: dict[str, object]) -> PaybisWebhookEvent | None:
        """Idempotent intake. Returns the parsed event on first sight, None on a duplicate.
        Raises (via parse_event) on a malformed payload. No signature trust in sandbox."""
        event = parse_event(payload)
        key = event.idempotency_key  # raises if no partnerOrderId/transactionId
        if key in self._seen:
            self.duplicates += 1
            return None
        self._seen.add(key)
        self.events.append(event)
        return event
