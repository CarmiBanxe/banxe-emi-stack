"""Tests for sync_ollama_ctx GUARDED action and _parse_ctx_value helper.

Coverage: happy path, circuit breaker, SSH failures, backup/patch/rollback,
audit record invariants, secret-in-log guard, CB lifecycle, baseline param.
21 tests (≥ 15 required by spec).
"""

from __future__ import annotations

from services.watchdog.audit_log import AuditRecord, InMemoryAuditLog
from services.watchdog.circuit_breaker import CBState
from services.watchdog.decision_policy import RepairAction
from services.watchdog.guarded_actions import (
    _CTX_KEY,
    _OVERRIDE_CONF,
    GuardedActionExecutor,
    _parse_ctx_value,
)

_NODE = "evo1"
_READ_CMD = ["ssh", _NODE, "grep", _CTX_KEY, _OVERRIDE_CONF]
_BACKUP_CMD = ["ssh", _NODE, "cp", _OVERRIDE_CONF, f"{_OVERRIDE_CONF}.bak"]
_SED_CMD_8192 = [
    "ssh",
    _NODE,
    "sed",
    "-i",
    f"s|{_CTX_KEY}=[0-9]*|{_CTX_KEY}=8192|g",
    _OVERRIDE_CONF,
]
_RELOAD_CMD = ["ssh", _NODE, "sudo", "systemctl", "daemon-reload"]
_RESTART_CMD = ["ssh", _NODE, "sudo", "systemctl", "restart", "ollama"]
_ROLLBACK_CMD = ["ssh", _NODE, "cp", f"{_OVERRIDE_CONF}.bak", _OVERRIDE_CONF]


class _SeqShellPort:
    """Sequential-response test shell stub.

    Each add(cmd, *responses) pre-loads a dequeue for that command key.
    On each call the front item is popped; when only one remains it is
    returned repeatedly.  Exceptions in the queue are raised when dequeued.
    """

    def __init__(self) -> None:
        self._seq: dict[str, list[tuple[int, str] | BaseException]] = {}
        self.calls: list[list[str]] = []

    def add(self, cmd: list[str], *responses: tuple[int, str] | BaseException) -> None:
        self._seq[" ".join(cmd)] = list(responses)

    async def run(self, cmd: list[str], *, timeout: float = 30.0) -> tuple[int, str]:
        self.calls.append(list(cmd))
        key = " ".join(cmd)
        seq = self._seq.get(key, [(0, "")])
        resp = seq.pop(0) if len(seq) > 1 else (seq[0] if seq else (0, ""))
        if isinstance(resp, BaseException):
            raise resp
        return resp


def _make_executor(
    shell: _SeqShellPort, *, now: float = 1000.0
) -> tuple[GuardedActionExecutor, InMemoryAuditLog]:
    audit = InMemoryAuditLog()
    executor = GuardedActionExecutor(
        shell_port=shell,
        audit_port=audit,
        cb_max_attempts=3,
        cb_backoff_base_s=10.0,
        cb_max_quarantine_s=1800.0,
        now_fn=lambda: now,
    )
    return executor, audit


def _happy_shell(drift_value: str = "131072") -> _SeqShellPort:
    """Shell pre-loaded for full success: drift detected → patched → verified."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}={drift_value}"), (0, f"{_CTX_KEY}=8192"))
    shell.add(_BACKUP_CMD, (0, ""))
    shell.add(_SED_CMD_8192, (0, ""))
    shell.add(_RELOAD_CMD, (0, ""))
    shell.add(_RESTART_CMD, (0, ""))
    return shell


# ── _parse_ctx_value (pure, no IO) ────────────────────────────────────────────


def test_parse_ctx_value_bare_format() -> None:
    assert _parse_ctx_value("OLLAMA_NUM_CTX=131072") == "131072"


def test_parse_ctx_value_environment_quoted_format() -> None:
    assert _parse_ctx_value('Environment="OLLAMA_NUM_CTX=131072"') == "131072"


def test_parse_ctx_value_no_match_returns_none() -> None:
    assert _parse_ctx_value("[Service]\nExecStart=/usr/bin/ollama serve") is None


def test_parse_ctx_value_baseline_value() -> None:
    assert _parse_ctx_value("OLLAMA_NUM_CTX=8192") == "8192"


# ── happy path ────────────────────────────────────────────────────────────────


async def test_sync_ollama_ctx_happy_path_returns_action() -> None:
    shell = _happy_shell()
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.SYNC_OLLAMA_CTX


async def test_sync_ollama_ctx_happy_path_two_audit_records() -> None:
    shell = _happy_shell()
    executor, audit = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    assert len(audit.records) == 2


async def test_sync_ollama_ctx_before_audit_executed_false() -> None:
    shell = _happy_shell()
    executor, audit = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    before: AuditRecord = audit.records[0]
    assert before.executed is False
    assert before.verification_result is None
    assert before.autonomy_mode == "GUARDED"


async def test_sync_ollama_ctx_after_audit_executed_true() -> None:
    shell = _happy_shell()
    executor, audit = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    after: AuditRecord = audit.records[1]
    assert after.executed is True
    assert after.verification_result is True


async def test_sync_ollama_ctx_no_raw_ctx_value_in_audit() -> None:
    """SECRETS-IN-LOG guard: raw drift value must not appear in any string audit field."""
    shell = _happy_shell("131072")
    executor, audit = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE, baseline_ctx=8192)
    leak_value = "131072"
    for rec in audit.records:
        for attr in (
            "observed_state",
            "root_cause",
            "selected_action",
            "autonomy_mode",
            "quick_fix",
            "llm_diagnosis",
            "upstream_cause",
        ):
            val: str = getattr(rec, attr, None) or ""
            assert leak_value not in val, f"drift value leaked into audit field {attr!r}: {val!r}"


# ── already-correct shortcut ──────────────────────────────────────────────────


async def test_sync_ollama_ctx_already_correct_returns_action() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=8192"))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.SYNC_OLLAMA_CTX


async def test_sync_ollama_ctx_already_correct_no_mutation_commands() -> None:
    """No backup/sed/restart commands sent when value already matches baseline."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=8192"))
    executor, _ = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    sent = {" ".join(c) for c in shell.calls}
    assert " ".join(_BACKUP_CMD) not in sent
    assert " ".join(_RESTART_CMD) not in sent


# ── SSH / read failures ───────────────────────────────────────────────────────


async def test_sync_ollama_ctx_read_fail_rc_nonzero_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (1, ""))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


async def test_sync_ollama_ctx_read_fail_ssh_exception_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, OSError("connection refused"))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


async def test_sync_ollama_ctx_backup_fail_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=131072"))
    shell.add(_BACKUP_CMD, (1, "permission denied"))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


async def test_sync_ollama_ctx_sed_fail_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=131072"))
    shell.add(_BACKUP_CMD, (0, ""))
    shell.add(_SED_CMD_8192, (1, ""))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


async def test_sync_ollama_ctx_restart_fail_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=131072"))
    shell.add(_BACKUP_CMD, (0, ""))
    shell.add(_SED_CMD_8192, (0, ""))
    shell.add(_RELOAD_CMD, (0, ""))
    shell.add(_RESTART_CMD, (1, ""))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


# ── verify failure + rollback ─────────────────────────────────────────────────


async def test_sync_ollama_ctx_verify_fail_escalates() -> None:
    """Patch succeeds but re-read still shows drift → ESCALATE."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=131072"), (0, f"{_CTX_KEY}=131072"))
    shell.add(_BACKUP_CMD, (0, ""))
    shell.add(_SED_CMD_8192, (0, ""))
    shell.add(_RELOAD_CMD, (0, ""))
    shell.add(_RESTART_CMD, (0, ""))
    shell.add(_ROLLBACK_CMD, (0, ""))
    executor, _ = _make_executor(shell)
    assert await executor.sync_ollama_ctx(_NODE) == RepairAction.ESCALATE


async def test_sync_ollama_ctx_verify_fail_sends_rollback_cmd() -> None:
    """On verify failure, rollback cp .bak is issued to restore override.conf."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=131072"), (0, f"{_CTX_KEY}=131072"))
    shell.add(_BACKUP_CMD, (0, ""))
    shell.add(_SED_CMD_8192, (0, ""))
    shell.add(_RELOAD_CMD, (0, ""))
    shell.add(_RESTART_CMD, (0, ""))
    shell.add(_ROLLBACK_CMD, (0, ""))
    executor, _ = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    sent = {" ".join(c) for c in shell.calls}
    assert " ".join(_ROLLBACK_CMD) in sent


# ── circuit breaker ───────────────────────────────────────────────────────────


async def test_sync_ollama_ctx_cb_open_after_max_failures() -> None:
    """CB opens after max_attempts=3 failures; 4th call returns ESCALATE + CB audit."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (1, ""))  # always fails
    executor, audit = _make_executor(shell, now=1000.0)
    for _ in range(3):
        await executor.sync_ollama_ctx(_NODE)
    result = await executor.sync_ollama_ctx(_NODE)
    assert result == RepairAction.ESCALATE
    cb_open = [r for r in audit.records if r.autonomy_mode == "GUARDED_CB_OPEN"]
    assert len(cb_open) >= 1


async def test_sync_ollama_ctx_cb_resets_to_zero_on_success() -> None:
    """Successful sync resets CB to CLOSED with attempts=0."""
    shell = _happy_shell()
    executor, _ = _make_executor(shell)
    await executor.sync_ollama_ctx(_NODE)
    cb = executor._breakers.get(f"sync_ollama_ctx:{_NODE}")
    assert cb is not None
    assert cb.attempts == 0
    assert cb._state == CBState.CLOSED


# ── baseline parameterisation ─────────────────────────────────────────────────


async def test_sync_ollama_ctx_custom_baseline_4096() -> None:
    """baseline_ctx=4096 appears in the sed expression sent over SSH."""
    shell = _SeqShellPort()
    shell.add(_READ_CMD, (0, f"{_CTX_KEY}=65536"), (0, f"{_CTX_KEY}=4096"))
    shell.add(_BACKUP_CMD, (0, ""))
    sed_4096 = [
        "ssh",
        _NODE,
        "sed",
        "-i",
        f"s|{_CTX_KEY}=[0-9]*|{_CTX_KEY}=4096|g",
        _OVERRIDE_CONF,
    ]
    shell.add(sed_4096, (0, ""))
    shell.add(_RELOAD_CMD, (0, ""))
    shell.add(_RESTART_CMD, (0, ""))
    executor, _ = _make_executor(shell)
    result = await executor.sync_ollama_ctx(_NODE, baseline_ctx=4096)
    assert result == RepairAction.SYNC_OLLAMA_CTX
    sent_strs = [" ".join(c) for c in shell.calls]
    assert any("4096" in s and "sed" in s for s in sent_strs)
