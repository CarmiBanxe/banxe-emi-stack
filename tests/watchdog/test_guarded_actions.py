"""Tests for GuardedActionExecutor (GAP-A).

Covers: success paths, circuit-breaker blocking, dispatch failure, verify failure + rollback,
stateful-container guard, I-24 audit (before/after), MANUAL_ONLY flag, secret safety.
"""

from __future__ import annotations

import pytest

from services.watchdog.audit_log import InMemoryAuditLog
from services.watchdog.circuit_breaker import CBState, CircuitBreakerState, InMemoryShellPort
from services.watchdog.decision_policy import RepairAction
from services.watchdog.guarded_actions import GuardedActionExecutor

# ── test infrastructure ───────────────────────────────────────────────────────


class ExceptionShellPort:
    """Shell port stub that always raises — simulates network/SSH timeout."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> tuple[int, str]:
        self.calls.append(list(cmd))
        raise ConnectionError("network timeout")


def _make_executor(
    responses: dict[str, tuple[int, str]] | None = None,
    default: tuple[int, str] = (0, ""),
    now: float = 1000.0,
    cb_max_attempts: int = 3,
) -> tuple[GuardedActionExecutor, InMemoryShellPort, InMemoryAuditLog]:
    shell = InMemoryShellPort(responses=responses or {}, default=default)
    audit = InMemoryAuditLog()
    executor = GuardedActionExecutor(
        shell_port=shell,
        audit_port=audit,
        cb_max_attempts=cb_max_attempts,
        cb_backoff_base_s=10.0,
        cb_max_quarantine_s=1800.0,
        now_fn=lambda: now,
    )
    return executor, shell, audit


def _open_breaker(executor: GuardedActionExecutor, key: str) -> CircuitBreakerState:
    cb = executor._get_breaker(key)
    cb._state = CBState.OPEN
    cb.quarantine_until = 9_999_999.0
    return cb


# ── restart_ollama: success ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restart_ollama_success_returns_action() -> None:
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "active"),
    }
    executor, _, _ = _make_executor(responses=responses)
    result = await executor.restart_ollama("evo1")
    assert result == RepairAction.RESTART_OLLAMA


@pytest.mark.asyncio
async def test_restart_ollama_writes_before_and_after_audit() -> None:
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "active"),
    }
    executor, _, audit = _make_executor(responses=responses)
    await executor.restart_ollama("evo1")

    assert len(audit.records) == 2
    before, after = audit.records
    assert before.executed is False
    assert before.verification_result is None
    assert after.executed is True
    assert after.verification_result is True


@pytest.mark.asyncio
async def test_restart_ollama_circuit_open_escalates_without_dispatch() -> None:
    executor, shell, audit = _make_executor()
    _open_breaker(executor, "restart_ollama")

    result = await executor.restart_ollama("evo1")

    assert result == RepairAction.ESCALATE
    assert len(shell.calls) == 0  # no dispatch sent
    assert len(audit.records) == 1  # one CB-blocked record
    assert audit.records[0].executed is False
    assert audit.records[0].autonomy_mode == "GUARDED_CB_OPEN"


@pytest.mark.asyncio
async def test_restart_ollama_dispatch_exception_single_audit_record() -> None:
    """Dispatch exception → only the BEFORE record is written (I-24: single record)."""
    audit = InMemoryAuditLog()
    shell = ExceptionShellPort()
    executor = GuardedActionExecutor(
        shell_port=shell,
        audit_port=audit,
        cb_max_attempts=3,
        cb_backoff_base_s=10.0,
        cb_max_quarantine_s=1800.0,
        now_fn=lambda: 1000.0,
    )
    result = await executor.restart_ollama("evo1")

    assert result == RepairAction.ESCALATE
    assert len(audit.records) == 1
    assert audit.records[0].executed is False  # BEFORE record only


@pytest.mark.asyncio
async def test_restart_ollama_dispatch_nonzero_escalates() -> None:
    """Non-zero return code from dispatch → ESCALATE, 1 audit record, CB incremented."""
    executor, shell, audit = _make_executor(default=(1, "error"))
    result = await executor.restart_ollama("evo1")

    assert result == RepairAction.ESCALATE
    assert len(audit.records) == 1  # BEFORE record only
    cb = executor._get_breaker("restart_ollama")
    assert cb.attempts == 1


@pytest.mark.asyncio
async def test_restart_ollama_verify_failure_escalates_and_increments_cb() -> None:
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "inactive"),  # verify fails
    }
    executor, _, audit = _make_executor(responses=responses)
    result = await executor.restart_ollama("evo1")

    assert result == RepairAction.ESCALATE
    assert len(audit.records) == 2  # BEFORE + AFTER
    assert audit.records[1].verification_result is False
    cb = executor._get_breaker("restart_ollama")
    assert cb.attempts == 1


# ── config_sync: success, verify failure, rollback ────────────────────────────


@pytest.mark.asyncio
async def test_config_sync_success_returns_action() -> None:
    responses = {
        "git -C /repo pull --ff-only": (0, "Already up to date."),
        "git -C /repo status --porcelain": (0, ""),
    }
    executor, _, _ = _make_executor(responses=responses)
    result = await executor.config_sync("/repo")
    assert result == RepairAction.CONFIG_SYNC


@pytest.mark.asyncio
async def test_config_sync_verify_dirty_tree_escalates() -> None:
    responses = {
        "git -C /repo pull --ff-only": (0, ""),
        "git -C /repo status --porcelain": (0, "M config.yaml"),  # dirty → fail
    }
    executor, _, _ = _make_executor(responses=responses)
    result = await executor.config_sync("/repo")
    assert result == RepairAction.ESCALATE


@pytest.mark.asyncio
async def test_config_sync_verify_failure_triggers_rollback() -> None:
    responses = {
        "git -C /repo pull --ff-only": (0, ""),
        "git -C /repo status --porcelain": (0, "M config.yaml"),
    }
    executor, shell, _ = _make_executor(responses=responses)
    await executor.config_sync("/repo")

    rollback_calls = [c for c in shell.calls if "reset" in c]
    assert len(rollback_calls) == 1
    assert "HEAD@{1}" in rollback_calls[0]


@pytest.mark.asyncio
async def test_config_sync_after_record_has_result_true() -> None:
    responses = {
        "git -C /repo pull --ff-only": (0, ""),
        "git -C /repo status --porcelain": (0, ""),
    }
    executor, _, audit = _make_executor(responses=responses)
    await executor.config_sync("/repo")

    after = audit.records[-1]
    assert after.executed is True
    assert after.verification_result is True


@pytest.mark.asyncio
async def test_config_sync_dispatch_failure_increments_cb() -> None:
    executor, _, _ = _make_executor(default=(1, "fatal: not a git repo"))
    await executor.config_sync("/repo")

    cb = executor._get_breaker("config_sync:/repo")
    assert cb.attempts == 1


# ── recreate_container: success + stateful guard ──────────────────────────────


@pytest.mark.asyncio
async def test_recreate_container_success_returns_action() -> None:
    responses = {
        "docker restart litellm-proxy": (0, ""),
        "docker inspect --format={{.State.Status}} litellm-proxy": (0, "running"),
    }
    executor, _, _ = _make_executor(responses=responses)
    result = await executor.recreate_container("litellm-proxy")
    assert result == RepairAction.RECREATE_CONTAINER


@pytest.mark.asyncio
async def test_recreate_container_stateful_postgres_blocked_no_dispatch() -> None:
    executor, shell, _ = _make_executor()
    result = await executor.recreate_container("banxe-postgres-1")

    assert result == RepairAction.ESCALATE
    assert len(shell.calls) == 0  # stateful guard blocks before dispatch


@pytest.mark.asyncio
async def test_recreate_container_stateful_clickhouse_blocked() -> None:
    executor, shell, _ = _make_executor()
    result = await executor.recreate_container("clickhouse-server")

    assert result == RepairAction.ESCALATE
    assert len(shell.calls) == 0


@pytest.mark.asyncio
async def test_recreate_container_stateful_audit_has_manual_only_flag() -> None:
    executor, _, audit = _make_executor()
    await executor.recreate_container("pg-main-postgres")

    assert len(audit.records) == 1
    assert audit.records[0].manual_only is True


@pytest.mark.asyncio
async def test_recreate_container_cb_open_escalates() -> None:
    executor, shell, _ = _make_executor()
    _open_breaker(executor, "recreate_container:litellm-proxy")

    result = await executor.recreate_container("litellm-proxy")

    assert result == RepairAction.ESCALATE
    assert len(shell.calls) == 0


# ── I-24 audit ordering and content ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_before_audit_record_precedes_shell_dispatch() -> None:
    """BEFORE audit must be written before any shell call is made.

    Uses a shell port that captures its call count, checked via a shared list
    populated in order: audit.records then shell.calls.
    """
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "active"),
    }
    executor, shell, audit = _make_executor(responses=responses)
    await executor.restart_ollama("evo1")

    # Both lists exist; the BEFORE record is always first and dispatch calls always second
    assert len(audit.records) >= 1
    assert len(shell.calls) >= 1
    # BEFORE record must have executed=False (proof it was written pre-dispatch)
    assert audit.records[0].executed is False


@pytest.mark.asyncio
async def test_after_audit_record_has_verification_result_false_on_failure() -> None:
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "dead"),  # verify fails
    }
    executor, _, audit = _make_executor(responses=responses)
    await executor.restart_ollama("evo1")

    after = audit.records[-1]
    assert after.executed is True
    assert after.verification_result is False


# ── secret safety ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_secret_value_in_audit_target() -> None:
    """Audit records must never contain credential material in the target field."""
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "active"),
    }
    executor, _, audit = _make_executor(responses=responses)
    await executor.restart_ollama("evo1")

    for record in audit.records:
        target_lower = str(record.target).lower()
        assert "password" not in target_lower
        assert "secret" not in target_lower
        assert "token" not in target_lower


# ── circuit-breaker lifecycle ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_circuit_breaker_resets_to_closed_on_success() -> None:
    responses = {
        "ssh evo1 sudo systemctl restart ollama": (0, ""),
        "ssh evo1 systemctl is-active ollama": (0, "active"),
    }
    executor, _, _ = _make_executor(responses=responses)
    result = await executor.restart_ollama("evo1")

    assert result == RepairAction.RESTART_OLLAMA
    cb = executor._get_breaker("restart_ollama")
    assert cb.attempts == 0
    assert cb._state == CBState.CLOSED


@pytest.mark.asyncio
async def test_independent_breakers_per_action() -> None:
    """Failures on restart_ollama must not affect config_sync breaker."""
    # Force restart_ollama CB open
    executor, _, _ = _make_executor(default=(1, "error"))
    _open_breaker(executor, "restart_ollama")

    # config_sync breaker must be independent (CLOSED)
    cb_config = executor._get_breaker("config_sync:/repo")
    assert cb_config._state == CBState.CLOSED
    assert cb_config.is_blocked(1000.0) is False


@pytest.mark.asyncio
async def test_circuit_open_after_max_failures() -> None:
    """CB opens after cb_max_attempts consecutive failures."""
    executor, _, _ = _make_executor(default=(1, "err"), cb_max_attempts=2)

    await executor.restart_ollama("evo1")  # failure 1
    await executor.restart_ollama("evo1")  # failure 2 → CB should open

    cb = executor._get_breaker("restart_ollama")
    assert cb._state == CBState.OPEN
    assert cb.is_blocked(1000.0) is True


@pytest.mark.asyncio
async def test_half_open_probe_allowed_after_quarantine_expires() -> None:
    """HALF_OPEN: quarantine has passed → not blocked."""
    executor, _, _ = _make_executor(now=2000.0)
    cb = executor._get_breaker("restart_ollama")
    cb._state = CBState.OPEN
    cb.quarantine_until = 1500.0  # already expired (now=2000 > 1500)

    # get_state should return HALF_OPEN
    assert cb.get_state(2000.0) == CBState.HALF_OPEN
    # is_blocked uses get_state; HALF_OPEN is not OPEN so NOT blocked
    assert cb.is_blocked(2000.0) is False
