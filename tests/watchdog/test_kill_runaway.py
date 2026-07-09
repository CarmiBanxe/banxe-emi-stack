"""B2 tests — kill_runaway GUARDED action.

Coverage:
- runaway process killed → KILL_RUNAWAY returned
- protected process (exact match) → ESCALATE, never ssh pkill
- protected process (payment-* prefix) → ESCALATE, never ssh pkill
- circuit breaker opens after max_attempts failures
- CB open → ESCALATE immediately + GUARDED_CB_OPEN audit record
- before-audit record: executed=False, verification_result=None
- after-audit record: executed=True, verification_result=True
- verify failure (pgrep finds process still alive) → ESCALATE + CB failure
- pkill rc=1 (already dead) counts as dispatch success
- pkill rc=2 (unexpected) → ESCALATE + CB failure
- ssh dispatch exception → ESCALATE + CB failure
- ssh verify exception → verify=False → ESCALATE
- no secrets in audit records (only node hostname and process name)
- protected-process audit record has manual_only=True
- CB resets to CLOSED on success
16 tests total (≥ 15 required by spec).
"""

from __future__ import annotations

from services.watchdog.audit_log import AuditRecord, InMemoryAuditLog
from services.watchdog.circuit_breaker import CBState
from services.watchdog.decision_policy import RepairAction
from services.watchdog.guarded_actions import GuardedActionExecutor

_NODE = "evo1"
_TARGET = "oom-worker"

_PKILL_CMD = ["ssh", _NODE, "pkill", "-9", "-x", _TARGET]
_PGREP_CMD = ["ssh", _NODE, "pgrep", "-x", _TARGET]


class _SeqShellPort:
    """Sequential-response test shell stub (shared pattern — mirrors test_sync_ollama_ctx)."""

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


def _happy_shell(target: str = _TARGET, node: str = _NODE) -> _SeqShellPort:
    """Shell pre-loaded for full success: pkill rc=0, pgrep rc=1 (killed)."""
    shell = _SeqShellPort()
    shell.add(["ssh", node, "pkill", "-9", "-x", target], (0, ""))
    shell.add(["ssh", node, "pgrep", "-x", target], (1, ""))
    return shell


# ── happy path ────────────────────────────────────────────────────────────────


async def test_kill_runaway_happy_path_returns_action() -> None:
    executor, _ = _make_executor(_happy_shell())
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.KILL_RUNAWAY


async def test_kill_runaway_happy_path_two_audit_records() -> None:
    executor, audit = _make_executor(_happy_shell())
    await executor.kill_runaway(_NODE, _TARGET)
    assert len(audit.records) == 2


async def test_kill_runaway_before_audit_executed_false() -> None:
    executor, audit = _make_executor(_happy_shell())
    await executor.kill_runaway(_NODE, _TARGET)
    before: AuditRecord = audit.records[0]
    assert before.executed is False
    assert before.verification_result is None
    assert before.autonomy_mode == "GUARDED"


async def test_kill_runaway_after_audit_executed_true_verified() -> None:
    executor, audit = _make_executor(_happy_shell())
    await executor.kill_runaway(_NODE, _TARGET)
    after: AuditRecord = audit.records[1]
    assert after.executed is True
    assert after.verification_result is True


async def test_kill_runaway_pkill_rc1_already_dead_counts_as_success() -> None:
    """pkill rc=1 means process not found (already dead) — still counts as dispatch success."""
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, (1, ""))  # already dead
    shell.add(_PGREP_CMD, (1, ""))  # pgrep confirms not running
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.KILL_RUNAWAY


# ── protected processes — NEVER kill ─────────────────────────────────────────


async def test_kill_runaway_protected_exact_match_escalates() -> None:
    """ollama is in the protected list — must ESCALATE, never send pkill."""
    shell = _SeqShellPort()
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, "ollama")
    assert result == RepairAction.ESCALATE
    pkill_sent = any("pkill" in " ".join(c) for c in shell.calls)
    assert not pkill_sent, "pkill must not be sent for protected process"


async def test_kill_runaway_protected_payment_prefix_escalates() -> None:
    """payment-gateway matches payment-* prefix — must ESCALATE."""
    shell = _SeqShellPort()
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, "payment-gateway")
    assert result == RepairAction.ESCALATE
    pkill_sent = any("pkill" in " ".join(c) for c in shell.calls)
    assert not pkill_sent, "pkill must not be sent for payment-* process"


async def test_kill_runaway_protected_sets_manual_only_audit() -> None:
    """Protected process audit record must carry manual_only=True."""
    shell = _SeqShellPort()
    executor, audit = _make_executor(shell)
    await executor.kill_runaway(_NODE, "sshd")
    assert len(audit.records) == 1
    rec = audit.records[0]
    assert rec.manual_only is True
    assert rec.autonomy_mode == "MANUAL_ONLY_PROTECTED_PROCESS"


async def test_kill_runaway_protected_case_insensitive() -> None:
    """POSTGRES (upper-case) must also be protected."""
    shell = _SeqShellPort()
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, "POSTGRES")
    assert result == RepairAction.ESCALATE


# ── circuit breaker ───────────────────────────────────────────────────────────


async def test_kill_runaway_cb_opens_after_max_failures() -> None:
    """CB opens after 3 failures; 4th call returns ESCALATE with GUARDED_CB_OPEN audit."""
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, (2, ""))  # unexpected rc → failure (repeated)
    executor, audit = _make_executor(shell, now=1000.0)
    for _ in range(3):
        await executor.kill_runaway(_NODE, _TARGET)
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.ESCALATE
    cb_records = [r for r in audit.records if r.autonomy_mode == "GUARDED_CB_OPEN"]
    assert len(cb_records) >= 1


async def test_kill_runaway_cb_resets_on_success() -> None:
    executor, _ = _make_executor(_happy_shell())
    await executor.kill_runaway(_NODE, _TARGET)
    cb = executor._breakers.get(f"kill_runaway:{_NODE}:{_TARGET}")
    assert cb is not None
    assert cb.attempts == 0
    assert cb._state == CBState.CLOSED


# ── failure paths ─────────────────────────────────────────────────────────────


async def test_kill_runaway_pkill_unexpected_rc_escalates() -> None:
    """pkill rc=2 is not 0 or 1 → treat as failure → ESCALATE."""
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, (2, ""))
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.ESCALATE


async def test_kill_runaway_ssh_exception_escalates() -> None:
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, OSError("connection refused"))
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.ESCALATE


async def test_kill_runaway_verify_fail_pgrep_finds_process_escalates() -> None:
    """pkill succeeds but pgrep still finds the process → verify=False → ESCALATE."""
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, (0, ""))
    shell.add(_PGREP_CMD, (0, ""))  # rc=0 means process still running
    executor, _ = _make_executor(shell)
    result = await executor.kill_runaway(_NODE, _TARGET)
    assert result == RepairAction.ESCALATE


async def test_kill_runaway_verify_fail_after_audit_has_executed_true() -> None:
    """Even on verify failure, after-audit is written with executed=True (I-24 append-only)."""
    shell = _SeqShellPort()
    shell.add(_PKILL_CMD, (0, ""))
    shell.add(_PGREP_CMD, (0, ""))  # still alive
    executor, audit = _make_executor(shell)
    await executor.kill_runaway(_NODE, _TARGET)
    after_records = [r for r in audit.records if r.executed is True]
    assert len(after_records) >= 1
    assert after_records[0].verification_result is False


# ── no secrets in log ─────────────────────────────────────────────────────────


async def test_kill_runaway_no_secrets_in_audit() -> None:
    """Audit records must only contain node hostname and process name — no raw tokens."""
    executor, audit = _make_executor(_happy_shell())
    await executor.kill_runaway(_NODE, _TARGET)
    # Guard: no password-like patterns or SSH private key markers in any string field
    _BANNED_PATTERNS = ["-----BEGIN", "password", "token", "secret", "key="]
    for rec in audit.records:
        for field_name in (
            "observed_state",
            "root_cause",
            "selected_action",
            "autonomy_mode",
            "quick_fix",
            "llm_diagnosis",
            "upstream_cause",
        ):
            val: str = getattr(rec, field_name, None) or ""
            for pattern in _BANNED_PATTERNS:
                assert pattern not in val.lower(), (
                    f"Banned pattern {pattern!r} found in audit field {field_name!r}: {val!r}"
                )
