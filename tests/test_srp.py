"""MIG genuine-gap #3 — advisory SRP handshake (SECURITY-SENSITIVE; descriptive, no real secrets).

characterization: SrpPort / SrpHandshakeDescriptor / SrpStage state-machine. contract: handshake shape;
fail-closed (unknown id / illegal transition); NO persisted secret-material (refs are placeholders).
fence: no midaz/ledger/kyc imports; no real crypto-secret/private-key persistence; no wall-clock calls;
no float; DI id-generator deterministic; collision-safe.
"""

from dataclasses import fields
from pathlib import Path

import pytest

from services.auth.srp import (
    PLACEHOLDER_REF,
    STAGE_TRANSITIONS,
    SandboxSrpProvider,
    SrpHandshakeDescriptor,
    SrpPort,
    SrpStage,
)


def _p() -> SandboxSrpProvider:
    return SandboxSrpProvider()


def test_port_and_descriptor_and_state_machine() -> None:
    assert issubclass(SandboxSrpProvider, SrpPort)
    assert {f.name for f in fields(SrpHandshakeDescriptor)} == {
        "handshake_id",
        "user_ref",
        "stage",
        "salt_ref",
        "verifier_ref",
        "challenge_ref",
        "timestamp",
        "source",
    }
    assert {s.value for s in SrpStage} == {
        "registration",
        "challenge",
        "proof",
        "verified",
        "rejected",
    }
    assert STAGE_TRANSITIONS[SrpStage.VERIFIED] == () and STAGE_TRANSITIONS[SrpStage.REJECTED] == ()


def test_start_no_real_secret_material() -> None:
    d = _p().start_handshake(user_ref="user-opaque", timestamp="2026-06-21T22:40:00Z")
    assert d.stage is SrpStage.REGISTRATION
    # NO real crypto material — placeholders only
    assert d.salt_ref == PLACEHOLDER_REF
    assert d.verifier_ref == PLACEHOLDER_REF
    assert d.challenge_ref == PLACEHOLDER_REF
    assert d.timestamp == "2026-06-21T22:40:00Z"  # caller-supplied


def test_advance_state_machine_and_illegal_transition() -> None:
    p = _p()
    d = p.start_handshake(user_ref="u", timestamp="t0")
    c = p.advance(handshake_id=d.handshake_id, to_stage=SrpStage.CHALLENGE, timestamp="t1")
    assert c.stage is SrpStage.CHALLENGE
    with pytest.raises(ValueError):  # illegal: challenge -> verified (must go via proof)
        p.advance(handshake_id=d.handshake_id, to_stage=SrpStage.VERIFIED, timestamp="t2")


def test_fail_closed_unknown() -> None:
    p = _p()
    assert p.get_handshake("SRP-nope") is None
    with pytest.raises(KeyError):
        p.advance(handshake_id="SRP-nope", to_stage=SrpStage.CHALLENGE, timestamp="t")


def test_di_id_generator_and_collision_safe() -> None:
    seq = iter(["SRP-aaa", "SRP-bbb"])
    p = SandboxSrpProvider(id_generator=lambda: next(seq))
    assert p.start_handshake(user_ref="u", timestamp="t").handshake_id == "SRP-aaa"
    const = SandboxSrpProvider(id_generator=lambda: "SRP-fixed")
    const.start_handshake(user_ref="u", timestamp="t")
    with pytest.raises(RuntimeError):  # collision fail-closed, no overwrite
        const.start_handshake(user_ref="u2", timestamp="t")
    assert len([h for h in const._by_id]) == 1


def test_fence_no_secrets_no_wallclock_no_float() -> None:
    import services.auth.srp as mod

    text = Path(mod.__file__).read_text()
    low = text.lower()
    import_lines = "\n".join(
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import: {bad}"
    # no real secret-material persistence (no private-key / raw secret value fields/usage)
    assert "private_key" not in low and "privatekey" not in low and "secret_key" not in low
    # no wall-clock CALLS (docstring may mention the names)
    assert "datetime.now(" not in low and ".utcnow(" not in low and "date.now(" not in low
    # no float usage
    assert "float(" not in text and ": float" not in text and "-> float" not in text
