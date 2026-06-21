"""services/auth/srp.py — Advisory SRP (secure-remote-password) handshake surface (MIG genuine-gap #3).

SECURITY-SENSITIVE — descriptive / sandbox ONLY. Semantic port for the legacy `srp.service.ts`.
This module models the **SRP handshake state-machine** (registration -> challenge -> proof ->
verified/rejected) with **placeholder references only** — it holds NO real cryptographic material
(no real salt, verifier, private key, or proof), **persists NO secret material**, performs NO live
authentication, and does NOT duplicate `AuthApplicationService` / SCA (it is an additive login-strategy
sibling). Calls NO Midaz LedgerPort; touches NO KYC/KYB/AML; mutates NO ledger/state.

Time discipline: ``timestamp`` is caller-supplied (no wall-clock / `datetime.now` / `Date.now`).
ID generation is injected via constructor (DI; collision-safe). Fail-closed (unknown id / illegal
transition). No monetary numerics, no float (I-01 trivially).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import secrets

SANDBOX_SOURCE = "sandbox-mock"
#: Non-secret placeholder marker — descriptors carry NO real crypto material (sandbox only).
PLACEHOLDER_REF = "sandbox-placeholder"
_MAX_ID_ATTEMPTS = 5


def _default_handshake_id() -> str:
    """Safe default handshake-id generator (overridable via constructor DI)."""
    return f"SRP-{secrets.token_hex(6)}"


class SrpStage(str, Enum):
    """SRP handshake state-machine stages (descriptive)."""

    REGISTRATION = "registration"
    CHALLENGE = "challenge"
    PROOF = "proof"
    VERIFIED = "verified"
    REJECTED = "rejected"


#: Allowed advisory stage transitions (state-machine; no live side effects).
STAGE_TRANSITIONS: dict[SrpStage, tuple[SrpStage, ...]] = {
    SrpStage.REGISTRATION: (SrpStage.CHALLENGE, SrpStage.REJECTED),
    SrpStage.CHALLENGE: (SrpStage.PROOF, SrpStage.REJECTED),
    SrpStage.PROOF: (SrpStage.VERIFIED, SrpStage.REJECTED),
    SrpStage.VERIFIED: (),
    SrpStage.REJECTED: (),
}


@dataclass(frozen=True)
class SrpHandshakeDescriptor:
    """Descriptive SRP handshake record — placeholder refs ONLY, no real secret material.

    salt_ref / verifier_ref / challenge_ref are sandbox placeholders (never real crypto values), are
    NOT persisted as secrets, and never leave the descriptive layer.
    """

    handshake_id: str
    user_ref: str  # opaque/descriptive (not raw PII)
    stage: SrpStage
    salt_ref: str  # placeholder marker only
    verifier_ref: str  # placeholder marker only
    challenge_ref: str  # placeholder marker only
    timestamp: str  # caller-supplied (no wall-clock)
    source: str = SANDBOX_SOURCE


class SrpPort(ABC):
    """Read-only advisory SRP handshake contract (descriptive; no real secrets; fail-closed)."""

    @abstractmethod
    def start_handshake(self, *, user_ref: str, timestamp: str) -> SrpHandshakeDescriptor:
        """Begin an advisory SRP handshake at REGISTRATION (placeholder refs; no real crypto in)."""

    @abstractmethod
    def advance(
        self, *, handshake_id: str, to_stage: SrpStage, timestamp: str
    ) -> SrpHandshakeDescriptor:
        """Advance the handshake state-machine (validated transition; fail-closed)."""

    @abstractmethod
    def get_handshake(self, handshake_id: str) -> SrpHandshakeDescriptor | None:
        """Return the handshake descriptor, or None if unknown (fail-closed)."""


class SandboxSrpProvider(SrpPort):
    """Sandbox config-as-data SRP provider — NO real crypto, NO secret-material persistence."""

    def __init__(self, *, id_generator: Callable[[], str] | None = None) -> None:
        # DI: id generation injected via constructor (safe default); no module singleton.
        self._by_id: dict[str, SrpHandshakeDescriptor] = {}
        self._gen_id: Callable[[], str] = id_generator or _default_handshake_id

    def start_handshake(self, *, user_ref: str, timestamp: str) -> SrpHandshakeDescriptor:
        handshake_id = self._gen_id()
        attempts = 0
        while handshake_id in self._by_id:  # collision-safe: never overwrite a prior handshake
            attempts += 1
            if attempts >= _MAX_ID_ATTEMPTS:
                raise RuntimeError("srp: could not generate a unique handshake_id (fail-closed)")
            handshake_id = self._gen_id()
        desc = SrpHandshakeDescriptor(
            handshake_id=handshake_id,
            user_ref=user_ref,
            stage=SrpStage.REGISTRATION,
            salt_ref=PLACEHOLDER_REF,  # no real salt
            verifier_ref=PLACEHOLDER_REF,  # no real verifier
            challenge_ref=PLACEHOLDER_REF,  # no real challenge
            timestamp=timestamp,
            source=SANDBOX_SOURCE,
        )
        self._by_id[handshake_id] = desc
        return desc

    def advance(
        self, *, handshake_id: str, to_stage: SrpStage, timestamp: str
    ) -> SrpHandshakeDescriptor:
        cur = self._by_id.get(handshake_id)
        if cur is None:
            raise KeyError(f"srp handshake not found: {handshake_id!r}")  # fail-closed
        if to_stage not in STAGE_TRANSITIONS[cur.stage]:
            raise ValueError(
                f"illegal SRP transition {cur.stage.value} -> {to_stage.value}"
            )  # fail-closed
        nxt = SrpHandshakeDescriptor(
            handshake_id=cur.handshake_id,
            user_ref=cur.user_ref,
            stage=to_stage,
            salt_ref=cur.salt_ref,
            verifier_ref=cur.verifier_ref,
            challenge_ref=cur.challenge_ref,
            timestamp=timestamp,
            source=SANDBOX_SOURCE,
        )
        self._by_id[handshake_id] = nxt
        return nxt

    def get_handshake(self, handshake_id: str) -> SrpHandshakeDescriptor | None:
        return self._by_id.get(handshake_id)  # fail-closed
