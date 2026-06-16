"""Tests for services/_legacy_common/state_machine.py."""

from __future__ import annotations

import pytest

from services._legacy_common.state_machine import assert_valid_transition, is_terminal
from services.shared.errors import BanxeLegacyAdapterError


class _TestError(BanxeLegacyAdapterError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message, code=code)


_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"ACTIVE", "CANCELLED"},
    "ACTIVE": {"COMPLETED", "CANCELLED"},
    "COMPLETED": set(),
    "CANCELLED": set(),
}

_TERMINALS: set[str] = {"COMPLETED", "CANCELLED"}


# ── assert_valid_transition ───────────────────────────────────────────────────


def test_valid_transition_does_not_raise() -> None:
    assert_valid_transition(
        current="PENDING",
        target="ACTIVE",
        transitions=_TRANSITIONS,
        adapter_error_cls=_TestError,
    )


def test_valid_transition_second_successor() -> None:
    assert_valid_transition(
        current="PENDING",
        target="CANCELLED",
        transitions=_TRANSITIONS,
        adapter_error_cls=_TestError,
    )


def test_invalid_transition_raises_with_correct_code() -> None:
    with pytest.raises(_TestError) as exc_info:
        assert_valid_transition(
            current="PENDING",
            target="COMPLETED",
            transitions=_TRANSITIONS,
            adapter_error_cls=_TestError,
        )
    assert exc_info.value.code == "invalid_state_transition"


def test_invalid_transition_message_contains_states() -> None:
    with pytest.raises(_TestError) as exc_info:
        assert_valid_transition(
            current="ACTIVE",
            target="PENDING",
            transitions=_TRANSITIONS,
            adapter_error_cls=_TestError,
        )
    msg = str(exc_info.value)
    assert "ACTIVE" in msg
    assert "PENDING" in msg


def test_transition_from_terminal_state_raises() -> None:
    with pytest.raises(_TestError) as exc_info:
        assert_valid_transition(
            current="COMPLETED",
            target="ACTIVE",
            transitions=_TRANSITIONS,
            adapter_error_cls=_TestError,
        )
    assert exc_info.value.code == "invalid_state_transition"


def test_transition_from_unknown_state_raises() -> None:
    with pytest.raises(_TestError) as exc_info:
        assert_valid_transition(
            current="UNKNOWN",
            target="ACTIVE",
            transitions=_TRANSITIONS,
            adapter_error_cls=_TestError,
        )
    assert exc_info.value.code == "invalid_state_transition"


def test_transition_to_self_raises_when_not_allowed() -> None:
    with pytest.raises(_TestError):
        assert_valid_transition(
            current="ACTIVE",
            target="ACTIVE",
            transitions=_TRANSITIONS,
            adapter_error_cls=_TestError,
        )


def test_transition_to_self_allowed_when_listed() -> None:
    transitions_with_self: dict[str, set[str]] = {
        "ACTIVE": {"ACTIVE", "COMPLETED"},
    }
    assert_valid_transition(
        current="ACTIVE",
        target="ACTIVE",
        transitions=transitions_with_self,
        adapter_error_cls=_TestError,
    )


def test_uses_provided_error_class() -> None:
    class _SpecialError(BanxeLegacyAdapterError):
        def __init__(self, message: str, *, code: str) -> None:
            super().__init__(message, code=code)

    with pytest.raises(_SpecialError):
        assert_valid_transition(
            current="PENDING",
            target="COMPLETED",
            transitions=_TRANSITIONS,
            adapter_error_cls=_SpecialError,
        )


def test_empty_transitions_dict_always_raises() -> None:
    with pytest.raises(_TestError):
        assert_valid_transition(
            current="PENDING",
            target="ACTIVE",
            transitions={},
            adapter_error_cls=_TestError,
        )


# ── is_terminal ───────────────────────────────────────────────────────────────


def test_is_terminal_returns_true_for_terminal_status() -> None:
    assert is_terminal("COMPLETED", _TERMINALS) is True


def test_is_terminal_returns_true_for_second_terminal() -> None:
    assert is_terminal("CANCELLED", _TERMINALS) is True


def test_is_terminal_returns_false_for_active_status() -> None:
    assert is_terminal("ACTIVE", _TERMINALS) is False


def test_is_terminal_returns_false_for_pending() -> None:
    assert is_terminal("PENDING", _TERMINALS) is False


def test_is_terminal_returns_false_for_unknown_status() -> None:
    assert is_terminal("GHOST", _TERMINALS) is False
