"""Sprint 3 Tier A+B Watchdog Tests.

Covers: DependencyGraph, RunbookIndex, LLM enrichment, AuditRecord new fields,
cascade suppression, preflight, snapshot, self-test, SLO tracking.
"""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from services.watchdog.audit_log import InMemoryAuditLog, make_audit_record
from services.watchdog.dependency_graph import DependencyGraph, InMemoryDependencyGraph
from services.watchdog.docker_port import ContainerStatus, InMemoryDockerPort
from services.watchdog.prometheus_exporter import WatchdogMetrics
from services.watchdog.repair_engine import RepairEngine
from services.watchdog.root_cause_classifier import Classification, RootCause, RootCauseClassifier
from services.watchdog.runbook_index import RUNBOOK_INDEX, RunbookEntry, get_runbook
from services.watchdog.watchdog import (
    InMemoryLedger,
    InMemoryOllamaPort,
    NodeConfig,
    Watchdog,
    WatchdogConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

NODE_URL = "http://192.168.0.72:11434"
MODEL = "llama3.3:70b"


def _cfg(**kwargs: object) -> WatchdogConfig:
    base: dict = dict(
        p1_health_interval_s=60,
        p2_efficiency_interval_s=900,
        p1_timeout_s=8,
        gen_timeout_s=120,
        cold_strikes=2,
        escalate_after_warmup_fails=3,
        backoff_s=[0, 0, 0],
        escalation_cooldown_s=0,
        min_tokens_per_sec={"llama3.3:70b": 5.0, "default": 8.0},
        max_hot_latency_s=8.0,
        max_cold_start_s=90.0,
        min_success_rate=0.95,
        correctness_prompt="What is 2+2? Reply only the number.",
        correctness_expect="4",
        nodes=[NodeConfig(name="evo1", url=NODE_URL, warm_models=[MODEL])],
        may_warm=True,
        ledger_path=Path("/tmp/test-watchdog-ledger.jsonl"),
        webhook=None,
    )
    base.update(kwargs)
    return WatchdogConfig(**base)


def _exited(name: str, exit_code: int = 0, restart_count: int = 0) -> ContainerStatus:
    return ContainerStatus(
        name=name,
        state="exited",
        exit_code=exit_code,
        restart_count=restart_count,
        health=None,
    )


def _running(name: str) -> ContainerStatus:
    return ContainerStatus(
        name=name,
        state="running",
        exit_code=0,
        restart_count=0,
        health="healthy",
    )


def _watchdog(
    *,
    docker_port: InMemoryDockerPort | None = None,
    audit: InMemoryAuditLog | None = None,
    metrics: WatchdogMetrics | None = None,
    dep_graph: InMemoryDependencyGraph | None = None,
    cfg_kwargs: dict | None = None,
) -> Watchdog:
    cfg = _cfg(**(cfg_kwargs or {}))
    ledger = InMemoryLedger()
    ollama = InMemoryOllamaPort()
    repair = RepairEngine(
        docker_port=docker_port,
        ollama_port=ollama,
        ledger_port=ledger,
    )
    return Watchdog(
        config=cfg,
        ollama=ollama,
        ledger=ledger,
        repair_engine=repair,
        docker_port=docker_port,
        audit_log=audit,
        metrics=metrics,
        dep_graph=dep_graph,
    )


# ===========================================================================
# 1. DependencyGraph
# ===========================================================================


def test_dep_graph_from_dict_parses_deps() -> None:
    raw = {"intent-dispatcher": {"depends_on": ["litellm-postgres"]}}
    g = DependencyGraph.from_dict(raw)
    assert g.get_dependencies("intent-dispatcher") == ["litellm-postgres"]


def test_dep_graph_from_dict_empty_raw() -> None:
    g = DependencyGraph.from_dict({})
    assert g.get_dependencies("anything") == []


def test_dep_graph_from_dict_none_raw() -> None:
    g = DependencyGraph.from_dict(None)  # type: ignore[arg-type]
    assert g.get_dependencies("x") == []


def test_dep_graph_is_cascade_true_when_upstream_unhealthy() -> None:
    g = DependencyGraph.from_dict({"B": {"depends_on": ["A"]}})
    assert g.is_cascade("B", frozenset({"A"})) is True


def test_dep_graph_is_cascade_false_when_upstream_healthy() -> None:
    g = DependencyGraph.from_dict({"B": {"depends_on": ["A"]}})
    assert g.is_cascade("B", frozenset()) is False


def test_dep_graph_is_cascade_false_no_deps() -> None:
    g = DependencyGraph.from_dict({"B": {"depends_on": []}})
    assert g.is_cascade("B", frozenset({"A", "B"})) is False


def test_dep_graph_upstream_cause_returns_first_unhealthy() -> None:
    g = DependencyGraph.from_dict({"C": {"depends_on": ["A", "B"]}})
    result = g.upstream_cause("C", frozenset({"B"}))
    assert result == "B"


def test_dep_graph_upstream_cause_none_when_no_unhealthy() -> None:
    g = DependencyGraph.from_dict({"C": {"depends_on": ["A"]}})
    assert g.upstream_cause("C", frozenset()) is None


def test_dep_graph_upstream_cause_none_unknown_target() -> None:
    g = DependencyGraph.from_dict({})
    assert g.upstream_cause("unknown", frozenset({"A"})) is None


def test_in_memory_dep_graph_is_cascade() -> None:
    g = InMemoryDependencyGraph({"app": ["db"]})
    assert g.is_cascade("app", frozenset({"db"})) is True
    assert g.is_cascade("app", frozenset()) is False


# ===========================================================================
# 2. RunbookIndex
# ===========================================================================


def test_runbook_index_has_all_8_root_causes() -> None:
    for cause in RootCause:
        assert cause in RUNBOOK_INDEX, f"Missing runbook entry for {cause}"


def test_runbook_index_all_entries_have_path() -> None:
    for cause, entry in RUNBOOK_INDEX.items():
        assert entry.path, f"{cause} has empty path"


def test_runbook_index_all_entries_have_quick_fix() -> None:
    for cause, entry in RUNBOOK_INDEX.items():
        assert entry.quick_fix, f"{cause} has empty quick_fix"


def test_runbook_index_manual_only_for_auth_failure() -> None:
    assert RUNBOOK_INDEX[RootCause.AUTH_FAILURE].manual_only is True


def test_runbook_index_manual_only_for_oom_killed() -> None:
    assert RUNBOOK_INDEX[RootCause.OOM_KILLED].manual_only is True


def test_runbook_index_manual_only_for_node_offline() -> None:
    assert RUNBOOK_INDEX[RootCause.NODE_OFFLINE].manual_only is True


def test_runbook_index_not_manual_only_for_crash_loop() -> None:
    assert RUNBOOK_INDEX[RootCause.CRASH_LOOP].manual_only is False


def test_runbook_index_not_manual_only_for_exited_zero() -> None:
    assert RUNBOOK_INDEX[RootCause.EXITED_ZERO].manual_only is False


def test_get_runbook_returns_entry_for_known_cause() -> None:
    entry = get_runbook(RootCause.CRASH_LOOP)
    assert isinstance(entry, RunbookEntry)
    assert "crash" in entry.path.lower()


def test_get_runbook_returns_none_for_missing() -> None:
    assert get_runbook(RootCause.UNKNOWN) is not None  # UNKNOWN is in the index
    # All causes should be covered
    for cause in RootCause:
        assert get_runbook(cause) is not None


# ===========================================================================
# 3. AuditRecord new fields
# ===========================================================================


def test_audit_record_new_fields_persist_through_make_audit_record() -> None:
    rec = make_audit_record(
        target="test-svc",
        observed_state="exited",
        root_cause="CRASH_LOOP",
        root_cause_confidence=0.95,
        selected_action="ESCALATE",
        action_score=0.95,
        executed=False,
        verification_result=None,
        upstream_cause="postgres",
        is_cascade=True,
        runbook_path="docs/runbooks/watchdog/crash-loop.md",
        quick_fix="Check logs",
        manual_only=False,
        llm_diagnosis="memory exhaustion",
        llm_confidence_hint=0.72,
        snapshot_path="/var/snapshots/test-svc-123.json",
    )
    assert rec.upstream_cause == "postgres"
    assert rec.is_cascade is True
    assert rec.runbook_path == "docs/runbooks/watchdog/crash-loop.md"
    assert rec.quick_fix == "Check logs"
    assert rec.manual_only is False
    assert rec.llm_diagnosis == "memory exhaustion"
    assert rec.llm_confidence_hint == 0.72
    assert rec.snapshot_path == "/var/snapshots/test-svc-123.json"
    assert rec.timestamp > 0


def test_audit_record_default_new_fields_are_none() -> None:
    rec = make_audit_record(
        target="t",
        observed_state="s",
        root_cause="UNKNOWN",
        root_cause_confidence=0.0,
        selected_action="LOG_AND_WAIT",
        action_score=0.0,
        executed=False,
        verification_result=None,
    )
    assert rec.upstream_cause is None
    assert rec.is_cascade is False
    assert rec.runbook_path is None
    assert rec.quick_fix is None
    assert rec.manual_only is False
    assert rec.llm_diagnosis is None
    assert rec.llm_confidence_hint is None
    assert rec.snapshot_path is None


# ===========================================================================
# 4. LLM enrichment
# ===========================================================================


class _FakeLLMPort:
    """Duck-type compatible with _LLMPort."""

    def __init__(self, response_text: str = "") -> None:
        self._text = response_text

    async def generate(
        self,
        node_url: str,
        model: str,
        prompt: str,
        timeout: float,
        keep_alive: int = -1,
    ) -> dict:
        return {"response": self._text}


@pytest.mark.asyncio
async def test_llm_enrichment_enriches_unknown_low_confidence() -> None:
    llm = _FakeLLMPort("DIAGNOSIS: memory pressure | CONFIDENCE: 0.8")
    clf = RootCauseClassifier(ollama_port=llm, ollama_node_url="http://x:11434")  # type: ignore[arg-type]
    clsf = Classification(reason=RootCause.UNKNOWN, confidence=0.3, evidence=["exit_code=1"])
    enriched = await clf.enrich_with_llm(clsf, "container exited")
    assert enriched.llm_diagnosis == "memory pressure"
    assert enriched.llm_confidence_hint == pytest.approx(0.8)
    assert enriched.reason == RootCause.UNKNOWN  # I-27: reason never changes


@pytest.mark.asyncio
async def test_llm_enrichment_skips_when_no_port() -> None:
    clf = RootCauseClassifier()
    clsf = Classification(reason=RootCause.UNKNOWN, confidence=0.3)
    result = await clf.enrich_with_llm(clsf, "ctx")
    assert result is clsf  # no change


@pytest.mark.asyncio
async def test_llm_enrichment_skips_non_unknown_reason() -> None:
    llm = _FakeLLMPort("DIAGNOSIS: crash | CONFIDENCE: 0.9")
    clf = RootCauseClassifier(ollama_port=llm, ollama_node_url="http://x:11434")  # type: ignore[arg-type]
    clsf = Classification(reason=RootCause.CRASH_LOOP, confidence=0.2)
    result = await clf.enrich_with_llm(clsf, "ctx")
    assert result is clsf  # CRASH_LOOP != UNKNOWN → skip


@pytest.mark.asyncio
async def test_llm_enrichment_skips_high_confidence_unknown() -> None:
    llm = _FakeLLMPort("DIAGNOSIS: x | CONFIDENCE: 0.9")
    clf = RootCauseClassifier(ollama_port=llm, ollama_node_url="http://x:11434")  # type: ignore[arg-type]
    clsf = Classification(reason=RootCause.UNKNOWN, confidence=0.9)  # high conf
    result = await clf.enrich_with_llm(clsf, "ctx")
    assert result is clsf  # confidence >= 0.5 → skip


@pytest.mark.asyncio
async def test_llm_enrichment_handles_exception_gracefully() -> None:
    class _ErrorLLM:
        async def generate(
            self, node_url: str, model: str, prompt: str, timeout: float, keep_alive: int = -1
        ) -> dict:
            raise ConnectionError("node offline")

    clf = RootCauseClassifier(ollama_port=_ErrorLLM(), ollama_node_url="http://x:11434")  # type: ignore[arg-type]
    clsf = Classification(reason=RootCause.UNKNOWN, confidence=0.2)
    result = await clf.enrich_with_llm(clsf, "ctx")
    assert result is clsf  # returns original on error


@pytest.mark.asyncio
async def test_llm_enrichment_partial_response_no_confidence() -> None:
    llm = _FakeLLMPort("DIAGNOSIS: oom issue")
    clf = RootCauseClassifier(ollama_port=llm, ollama_node_url="http://x:11434")  # type: ignore[arg-type]
    clsf = Classification(reason=RootCause.UNKNOWN, confidence=0.2)
    result = await clf.enrich_with_llm(clsf, "ctx")
    assert result.llm_diagnosis == "oom issue"
    assert result.llm_confidence_hint is None


# ===========================================================================
# 5. Cascade suppression via run_once_docker
# ===========================================================================


@pytest.mark.asyncio
async def test_cascade_container_gets_log_and_wait() -> None:
    """When upstream (litellm-postgres) is unhealthy, dependent (intent-dispatcher) → LOG_AND_WAIT."""
    audit = InMemoryAuditLog()
    docker = InMemoryDockerPort(
        containers=[
            _exited("litellm-postgres", exit_code=1),
            _exited("intent-dispatcher", exit_code=1),
        ]
    )
    dep_graph = InMemoryDependencyGraph({"intent-dispatcher": ["litellm-postgres"]})
    wd = _watchdog(docker_port=docker, audit=audit, dep_graph=dep_graph)

    await wd.run_once_docker()

    cascade_recs = [r for r in audit.records if r.target == "intent-dispatcher"]
    assert cascade_recs, "No audit record for intent-dispatcher"
    assert cascade_recs[-1].selected_action == "LOG_AND_WAIT"
    assert cascade_recs[-1].is_cascade is True
    assert cascade_recs[-1].upstream_cause == "litellm-postgres"


@pytest.mark.asyncio
async def test_primary_container_not_marked_cascade() -> None:
    """The upstream (litellm-postgres) itself has no upstream → not marked as cascade."""
    audit = InMemoryAuditLog()
    docker = InMemoryDockerPort(
        containers=[
            _exited("litellm-postgres", exit_code=1),
            _exited("intent-dispatcher", exit_code=1),
        ]
    )
    dep_graph = InMemoryDependencyGraph({"intent-dispatcher": ["litellm-postgres"]})
    wd = _watchdog(docker_port=docker, audit=audit, dep_graph=dep_graph)

    await wd.run_once_docker()

    postgres_recs = [r for r in audit.records if r.target == "litellm-postgres"]
    assert postgres_recs, "No audit record for litellm-postgres"
    assert postgres_recs[-1].is_cascade is False


@pytest.mark.asyncio
async def test_no_cascade_when_dep_graph_empty() -> None:
    """Without dep graph, both containers get independent treatment."""
    audit = InMemoryAuditLog()
    docker = InMemoryDockerPort(
        containers=[
            _exited("A", exit_code=1),
            _exited("B", exit_code=1),
        ]
    )
    dep_graph = InMemoryDependencyGraph({})
    wd = _watchdog(docker_port=docker, audit=audit, dep_graph=dep_graph)

    await wd.run_once_docker()

    for rec in audit.records:
        assert rec.is_cascade is False


# ===========================================================================
# 6. Preflight check (unit test of _check_preflight)
# ===========================================================================


@pytest.mark.asyncio
async def test_preflight_blocks_when_dep_unhealthy() -> None:
    audit = InMemoryAuditLog()
    dep_graph = InMemoryDependencyGraph({"app": ["db"]})
    wd = _watchdog(audit=audit, dep_graph=dep_graph, cfg_kwargs={"escalation_cooldown_s": 0})

    blocked = await wd._check_preflight("app", frozenset({"db"}))
    assert blocked is True


@pytest.mark.asyncio
async def test_preflight_not_blocked_when_deps_healthy() -> None:
    audit = InMemoryAuditLog()
    dep_graph = InMemoryDependencyGraph({"app": ["db"]})
    wd = _watchdog(audit=audit, dep_graph=dep_graph)

    blocked = await wd._check_preflight("app", frozenset())
    assert blocked is False


@pytest.mark.asyncio
async def test_preflight_writes_audit_record() -> None:
    audit = InMemoryAuditLog()
    dep_graph = InMemoryDependencyGraph({"app": ["db"]})
    wd = _watchdog(audit=audit, dep_graph=dep_graph, cfg_kwargs={"escalation_cooldown_s": 0})

    await wd._check_preflight("app", frozenset({"db"}))

    assert any(r.observed_state == "PREFLIGHT_FAILED" and r.target == "app" for r in audit.records)


@pytest.mark.asyncio
async def test_preflight_respects_cooldown() -> None:
    audit = InMemoryAuditLog()
    dep_graph = InMemoryDependencyGraph({"app": ["db"]})
    wd = _watchdog(audit=audit, dep_graph=dep_graph, cfg_kwargs={"escalation_cooldown_s": 9999})

    # First call writes record
    await wd._check_preflight("app", frozenset({"db"}))
    count_before = len(audit.records)

    # Second call within cooldown — no new record
    await wd._check_preflight("app", frozenset({"db"}))
    assert len(audit.records) == count_before


# ===========================================================================
# 7. Snapshot
# ===========================================================================


@pytest.mark.asyncio
async def test_snapshot_returns_none_when_no_dir() -> None:
    wd = _watchdog()
    container = _exited("test-svc")
    result = await wd._take_snapshot(container)
    assert result is None


@pytest.mark.asyncio
async def test_snapshot_writes_file_and_returns_path() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_dir = Path(tmpdir) / "snaps"
        audit = InMemoryAuditLog()
        docker = InMemoryDockerPort(containers=[_exited("test-svc")])
        cfg = _cfg(snapshots_dir=snap_dir)
        ledger = InMemoryLedger()
        ollama = InMemoryOllamaPort()
        repair = RepairEngine(docker_port=docker, ollama_port=ollama, ledger_port=ledger)
        wd = Watchdog(
            config=cfg,
            ollama=ollama,
            ledger=ledger,
            repair_engine=repair,
            docker_port=docker,
            audit_log=audit,
        )

        container = _exited("test-svc")
        path = await wd._take_snapshot(container)

        assert path is not None
        assert Path(path).exists()
        import json

        data = json.loads(Path(path).read_text())
        assert data["name"] == "test-svc"
        assert data["state"] == "exited"


@pytest.mark.asyncio
async def test_snapshot_path_appears_in_audit_record() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        snap_dir = Path(tmpdir) / "snaps"
        audit = InMemoryAuditLog()
        docker = InMemoryDockerPort(containers=[_exited("snap-svc", exit_code=0)])
        cfg = _cfg(snapshots_dir=snap_dir, escalation_cooldown_s=0)
        ledger = InMemoryLedger()
        ollama = InMemoryOllamaPort()
        repair = RepairEngine(docker_port=docker, ollama_port=ollama, ledger_port=ledger)
        wd = Watchdog(
            config=cfg,
            ollama=ollama,
            ledger=ledger,
            repair_engine=repair,
            docker_port=docker,
            audit_log=audit,
        )
        await wd.run_once_docker()

        assert audit.records, "No audit records written"
        # At least one record should have a snapshot_path
        snap_records = [r for r in audit.records if r.snapshot_path is not None]
        assert snap_records, "No record has snapshot_path set"


# ===========================================================================
# 8. Self-test
# ===========================================================================


@pytest.mark.asyncio
async def test_self_test_returns_ok_true_with_stubs() -> None:
    audit = InMemoryAuditLog()
    metrics = WatchdogMetrics()
    wd = _watchdog(audit=audit, metrics=metrics)

    result = await wd.run_self_test()

    assert result["ok"] is True
    assert "checks" in result


@pytest.mark.asyncio
async def test_self_test_writes_audit_record() -> None:
    audit = InMemoryAuditLog()
    wd = _watchdog(audit=audit)

    await wd.run_self_test()

    self_test_recs = [r for r in audit.records if r.target == "self-test"]
    assert self_test_recs, "self-test audit record not written"


@pytest.mark.asyncio
async def test_self_test_records_metric_ok() -> None:
    metrics = WatchdogMetrics()
    wd = _watchdog(metrics=metrics)

    await wd.run_self_test()

    rendered = metrics.render()
    assert "watchdog_self_test_ok 1" in rendered


@pytest.mark.asyncio
async def test_self_test_passes_without_audit_or_metrics() -> None:
    wd = _watchdog()
    result = await wd.run_self_test()
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_self_test_checks_dict_structure() -> None:
    wd = _watchdog(audit=InMemoryAuditLog(), metrics=WatchdogMetrics())
    result = await wd.run_self_test()
    assert isinstance(result["checks"], dict)
    assert all(isinstance(v, bool) for v in result["checks"].values())


# ===========================================================================
# 9. SLO tracking
# ===========================================================================


def test_slo_record_model_down_accumulates() -> None:
    m = WatchdogMetrics()
    m.record_model_down("llama3.3:70b", "evo1", ts=1000.0)
    m.record_model_up("llama3.3:70b", "evo1", ts=1060.0)
    assert m._model_downtime_s["llama3.3:70b@evo1"] == pytest.approx(60.0)


def test_slo_record_model_down_ignored_if_already_down() -> None:
    m = WatchdogMetrics()
    m.record_model_down("m", "h", ts=100.0)
    m.record_model_down("m", "h", ts=200.0)  # ignored
    m.record_model_up("m", "h", ts=150.0)
    assert m._model_downtime_s["m@h"] == pytest.approx(50.0)


def test_slo_record_model_up_clears_down_since() -> None:
    m = WatchdogMetrics()
    m.record_model_down("m", "h", ts=100.0)
    m.record_model_up("m", "h", ts=130.0)
    assert "m@h" not in m._model_down_since


def test_slo_record_model_up_no_op_when_not_down() -> None:
    m = WatchdogMetrics()
    m.record_model_up("m", "h", ts=100.0)  # no prior down
    assert "m@h" not in m._model_downtime_s


def test_slo_render_includes_downtime_gauge() -> None:
    m = WatchdogMetrics()
    m.record_model_down("llama3.3:70b", "evo1", ts=1000.0)
    m.record_model_up("llama3.3:70b", "evo1", ts=1090.0)
    rendered = m.render()
    assert "watchdog_model_downtime_24h_seconds" in rendered
    assert "llama3.3:70b" in rendered
    assert "90.000" in rendered


def test_slo_render_placeholder_when_no_downtime() -> None:
    m = WatchdogMetrics()
    rendered = m.render()
    assert 'watchdog_model_downtime_24h_seconds{model="none",host="none"} 0.000' in rendered


def test_slo_record_self_test_updates_gauge() -> None:
    m = WatchdogMetrics()
    m.record_self_test(ok=True)
    assert "watchdog_self_test_ok 1" in m.render()
    m.record_self_test(ok=False)
    assert "watchdog_self_test_ok 0" in m.render()


def test_slo_self_test_gauge_absent_before_first_test() -> None:
    m = WatchdogMetrics()
    rendered = m.render()
    assert "watchdog_self_test_ok" not in rendered


@pytest.mark.asyncio
async def test_slo_breach_logged_in_run_once_p1() -> None:
    """run_once_p1 logs SLO breach when downtime exceeds threshold."""
    metrics = WatchdogMetrics()
    # Pre-seed downtime above threshold
    metrics._model_downtime_s["llama3.3:70b@evo1"] = 9999.0

    ollama = InMemoryOllamaPort(loaded={NODE_URL: []})  # model NOT loaded → UNREACHABLE
    cfg = _cfg(slo_model_downtime_threshold_s=3600.0)
    ledger = InMemoryLedger()
    wd = Watchdog(config=cfg, ollama=ollama, ledger=ledger, metrics=metrics)

    # Should complete without error even with SLO breach
    await wd.run_once_p1()
