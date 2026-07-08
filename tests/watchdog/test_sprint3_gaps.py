"""Sprint 3 gap tests: RootCauseClassifier, AuditLog, WatchdogMetrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.watchdog.audit_log import (
    AuditRecord,
    FileAuditLog,
    InMemoryAuditLog,
    make_audit_record,
)
from services.watchdog.decision_policy import RepairAction
from services.watchdog.prometheus_exporter import WatchdogMetrics
from services.watchdog.root_cause_classifier import Classification, RootCause, RootCauseClassifier
from services.watchdog.watchdog import (
    InMemoryLedger,
    InMemoryOllamaPort,
    Watchdog,
    WatchdogConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cfg(**kwargs) -> WatchdogConfig:  # type: ignore[return]
    base: dict = {
        "p1_health_interval_s": 60,
        "p2_efficiency_interval_s": 900,
        "p1_timeout_s": 8,
        "gen_timeout_s": 30,
        "cold_strikes": 2,
        "escalate_after_warmup_fails": 3,
        "backoff_s": [1, 2, 4],
        "escalation_cooldown_s": 0,
        "min_tokens_per_sec": {"default": 8.0},
        "max_hot_latency_s": 5.0,
        "max_cold_start_s": 30.0,
        "min_success_rate": 0.9,
        "correctness_prompt": "2+2?",
        "correctness_expect": "4",
        "nodes": [],
        "may_warm": True,
        "ledger_path": Path("/tmp/wd-test.jsonl"),
        "webhook": None,
    }
    base.update(kwargs)
    return WatchdogConfig(**base)


clf = RootCauseClassifier()


# ---------------------------------------------------------------------------
# RootCauseClassifier tests
# ---------------------------------------------------------------------------


def test_classifier_crash_loop_restart_count():
    c = clf.classify(restart_count=15, crash_loop_threshold=10)
    assert c.reason == RootCause.CRASH_LOOP
    assert c.confidence >= 0.9


def test_classifier_oom_exit_code_137():
    c = clf.classify(exit_code=137, restart_count=0)
    assert c.reason == RootCause.OOM_KILLED
    assert c.confidence >= 0.8


def test_classifier_exited_zero():
    c = clf.classify(state="exited", exit_code=0, restart_count=0)
    assert c.reason == RootCause.EXITED_ZERO
    assert c.confidence == pytest.approx(1.0)


def test_classifier_auth_failure_from_log():
    c = clf.classify(logs=["authentication failed: bad credentials"], state="exited", exit_code=1)
    assert c.reason == RootCause.AUTH_FAILURE


def test_classifier_port_bind_failure_from_log():
    c = clf.classify(logs=["error: address already in use :8080"], state="exited", exit_code=1)
    assert c.reason == RootCause.PORT_BIND_FAILURE


def test_classifier_healthcheck_from_log():
    c = clf.classify(logs=["health check failed: probe timed out"], state="exited", exit_code=1)
    assert c.reason == RootCause.HEALTHCHECK_MISCONFIG


def test_classifier_restarting_state():
    c = clf.classify(state="restarting", restart_count=3, crash_loop_threshold=10)
    assert c.reason == RootCause.CRASH_LOOP


def test_classifier_node_offline_dead_state():
    c = clf.classify(state="dead", exit_code=1)
    assert c.reason == RootCause.NODE_OFFLINE


def test_classifier_unknown_fallback():
    c = clf.classify(state="running", exit_code=0, restart_count=0)
    assert c.reason == RootCause.UNKNOWN
    assert c.confidence < 0.5


def test_classifier_returns_classification_dataclass():
    c = clf.classify()
    assert isinstance(c, Classification)
    assert isinstance(c.reason, RootCause)
    assert isinstance(c.confidence, float)
    assert isinstance(c.evidence, list)


# ---------------------------------------------------------------------------
# AuditLog tests
# ---------------------------------------------------------------------------


def _make_record(**kwargs) -> AuditRecord:
    defaults = {
        "target": "container-a",
        "observed_state": "exited",
        "root_cause": "EXITED_ZERO",
        "root_cause_confidence": 1.0,
        "selected_action": "START_CONTAINER",
        "action_score": 0.9,
        "autonomy_mode": "AUTO",
        "executed": True,
        "verification_result": None,
    }
    defaults.update(kwargs)
    return make_audit_record(**defaults)  # type: ignore[arg-type]


def test_inmemory_audit_log_record_appends():
    log = InMemoryAuditLog()
    log.record(_make_record(target="c1"))
    log.record(_make_record(target="c2"))
    assert len(log.records) == 2
    assert log.records[0].target == "c1"
    assert log.records[1].target == "c2"


def test_inmemory_audit_log_is_append_only():
    log = InMemoryAuditLog()
    r = _make_record()
    log.record(r)
    original = log.records[0]
    log.record(_make_record(target="other"))
    assert log.records[0] is original  # first record unchanged


def test_file_audit_log_writes_valid_jsonl(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    log = FileAuditLog(path)
    log.record(_make_record(target="my-container"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    obj = json.loads(lines[0])
    assert obj["target"] == "my-container"
    assert "timestamp" in obj


def test_file_audit_log_appends_multiple_records(tmp_path: Path):
    path = tmp_path / "audit.jsonl"
    log = FileAuditLog(path)
    for i in range(5):
        log.record(_make_record(target=f"c{i}"))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 5


def test_make_audit_record_stamps_timestamp():
    r = _make_record()
    assert r.timestamp > 0


# ---------------------------------------------------------------------------
# WatchdogMetrics tests
# ---------------------------------------------------------------------------


def test_metrics_record_decision_increments_counter():
    m = WatchdogMetrics()
    m.record_decision("START_CONTAINER")
    m.record_decision("START_CONTAINER")
    m.record_decision("ESCALATE")
    assert m._decisions["START_CONTAINER"] == 2
    assert m._decisions["ESCALATE"] == 1


def test_metrics_record_repair_ok_increments_and_stamps():
    m = WatchdogMetrics()
    m.record_repair_ok()
    assert m._repairs_ok == 1
    assert m._last_success_ts > 0


def test_metrics_record_repair_fail():
    m = WatchdogMetrics()
    m.record_repair_fail()
    assert m._repairs_fail == 1


def test_metrics_set_unhealthy_targets():
    m = WatchdogMetrics()
    m.set_unhealthy_targets(3)
    assert m._targets_unhealthy == 3


def test_metrics_render_contains_all_families():
    m = WatchdogMetrics()
    m.record_decision("ESCALATE")
    m.record_repair_ok()
    m.record_escalation()
    m.set_unhealthy_targets(2)
    output = m.render()
    assert "watchdog_decisions_total" in output
    assert "watchdog_repairs_total" in output
    assert "watchdog_escalations_total" in output
    assert "watchdog_targets_unhealthy" in output
    assert "watchdog_last_success_timestamp" in output


# ---------------------------------------------------------------------------
# Integration: Watchdog.run_once_docker wires classifier + audit + metrics
# ---------------------------------------------------------------------------


class _FakeContainer:
    def __init__(
        self,
        name: str = "svc",
        state: str = "exited",
        exit_code: int = 0,
        restart_count: int = 0,
    ) -> None:
        self.name = name
        self.state = state
        self.exit_code = exit_code
        self.restart_count = restart_count


class _FakeDockerPort:
    def __init__(self, containers: list) -> None:
        self._containers = containers

    async def list_containers(self) -> list:
        return self._containers


class _FakeRepairEngine:
    def __init__(self, action: RepairAction = RepairAction.START_CONTAINER) -> None:
        self._action = action
        self.calls: list[tuple] = []

    async def evaluate_and_act(self, reason: str, context: dict) -> RepairAction:
        self.calls.append((reason, context))
        return self._action


@pytest.mark.asyncio
async def test_run_once_docker_records_audit_entry():
    audit = InMemoryAuditLog()
    metrics = WatchdogMetrics()
    engine = _FakeRepairEngine(RepairAction.START_CONTAINER)
    cfg = _cfg()
    wd = Watchdog(
        config=cfg,
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
        repair_engine=engine,
        docker_port=_FakeDockerPort([_FakeContainer(name="svc-a", state="exited", exit_code=0)]),
        root_cause_classifier=RootCauseClassifier(),
        audit_log=audit,
        metrics=metrics,
    )
    await wd.run_once_docker()
    assert len(audit.records) == 1
    assert audit.records[0].target == "svc-a"
    assert audit.records[0].executed is True


@pytest.mark.asyncio
async def test_run_once_docker_records_metrics():
    metrics = WatchdogMetrics()
    engine = _FakeRepairEngine(RepairAction.ESCALATE)
    cfg = _cfg()
    wd = Watchdog(
        config=cfg,
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
        repair_engine=engine,
        docker_port=_FakeDockerPort([_FakeContainer(name="svc-b", state="exited", exit_code=1)]),
        root_cause_classifier=RootCauseClassifier(),
        audit_log=InMemoryAuditLog(),
        metrics=metrics,
    )
    await wd.run_once_docker()
    assert metrics._decisions.get("ESCALATE", 0) == 1
    assert metrics._escalations == 1
    assert metrics._targets_unhealthy == 1


@pytest.mark.asyncio
async def test_run_once_docker_no_crash_when_no_optional_ports():
    engine = _FakeRepairEngine(RepairAction.LOG_AND_WAIT)
    cfg = _cfg()
    wd = Watchdog(
        config=cfg,
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
        repair_engine=engine,
        docker_port=_FakeDockerPort([_FakeContainer(name="svc-c", restart_count=15)]),
    )
    await wd.run_once_docker()
    assert len(engine.calls) == 1
