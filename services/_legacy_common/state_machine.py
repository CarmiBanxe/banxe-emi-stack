"""
services/_legacy_common/state_machine.py — Shared state machine helpers (Phase 5 tranche 3).

assert_valid_transition: single validator used by all legacy adapter advance_to() methods.
is_terminal: convenience check for adapters that guard against post-terminal operations.

Canon: ADR-025 §15-16 | Phase 5 tranche 3
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Any


def assert_valid_transition(
    *,
    current: str,
    target: str,
    transitions: Mapping[str, AbstractSet[str]],
    adapter_error_cls: type[Any],
    error_code: str = "invalid_state_transition",
) -> None:
    """
    Raise adapter_error_cls if target is not a valid successor of current.

    adapter_error_cls must accept (message: str, *, code: str) — same signature
    as BanxeLegacyAdapterError subclasses.

    error_code defaults to "invalid_state_transition" to match Sepa/Abs/SumSub.
    Pass error_code="invalid_transition" for BinanceKYC (historical divergence).
    """
    if target not in transitions.get(current, set()):
        raise adapter_error_cls(
            f"Illegal transition: {current} → {target}",
            code=error_code,
        )


def is_terminal(status: str, terminal_set: AbstractSet[str]) -> bool:
    """Return True if status is in terminal_set (no further transitions allowed)."""
    return status in terminal_set
