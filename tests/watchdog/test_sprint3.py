"""Sprint 3 Watchdog Tests — decision policy + docker monitoring + repair engine."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.watchdog.decision_policy import (
    SAFE_AUTO_THRESHOLD,
    ActionScore,
    DefaultActionScorer,
    RepairAction,
)
from services.watchdog.docker_port import ContainerStatus, InMemoryDockerPort
from services.watchdog.repair_engine import RepairEngine
from services.watchdog.watchdog import (
    InMemoryLedger,
    InMemoryOllamaPort,
    NodeConfig,
    Watchdog,
    WatchdogConfig,
)

NODE_URL = "http://192.168.0.72:11434"
MODEL = "llama3.3:70b"


def _cfg(**kwargs: object) -> WatchdogConfig:
    """Build test config."""
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


# ActionScore tests


def test_action_score_frozen_immutable() -> None:
    """ActionScore is frozen dataclass."""
    score = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.1,
        confidence=0.85,
        time_to_recovery_s=30.0,
    )
    with pytest.raises(AttributeError):
        score.action = RepairAction.ESCALATE  # type: ignore


def test_action_score_formula_calculates_correctly() -> None:
    """ActionScore.score property calculates: reversibility * confidence * (1.0 - blast_radius * 0.5)."""
    score = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.1,
        confidence=0.85,
        time_to_recovery_s=30.0,
    )
    # 1.0 * 0.85 * (1.0 - 0.1 * 0.5) = 0.85 * 0.95 = 0.8075
    expected = 1.0 * 0.85 * (1.0 - 0.1 * 0.5)
    assert abs(score.score - expected) < 0.0001


def test_action_score_high_blast_radius_reduces_score() -> None:
    """High blast_radius penalizes score."""
    score1 = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.1,
        confidence=0.85,
        time_to_recovery_s=30.0,
    )
    score2 = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.9,
        confidence=0.85,
        time_to_recovery_s=30.0,
    )
    assert score1.score > score2.score


def test_action_score_low_confidence_reduces_score() -> None:
    """Low confidence reduces score."""
    score1 = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.1,
        confidence=0.85,
        time_to_recovery_s=30.0,
    )
    score2 = ActionScore(
        action=RepairAction.WARM_MODEL,
        reversibility=1.0,
        blast_radius=0.1,
        confidence=0.3,
        time_to_recovery_s=30.0,
    )
    assert score1.score > score2.score


# DefaultActionScorer tests


def test_action_scorer_cold_strike_ranks_warm_highest() -> None:
    """COLD_STRIKE reason → WARM_MODEL scores highest."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("COLD_STRIKE", {"warmup_fails": 0})
    assert scores[0].action == RepairAction.WARM_MODEL
    assert scores[0].score >= SAFE_AUTO_THRESHOLD


def test_action_scorer_cold_strike_multiple_fails_adds_escalate() -> None:
    """COLD_STRIKE with warmup_fails>=2 → adds ESCALATE option."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("COLD_STRIKE", {"warmup_fails": 2})
    actions = [s.action for s in scores]
    assert RepairAction.WARM_MODEL in actions
    assert RepairAction.ESCALATE in actions


def test_action_scorer_exited_clean_ranks_start_container_highest() -> None:
    """Exited(0) reason → START_CONTAINER scores highest."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions(
        "Exited(0)",
        {"restart_count": 5, "crash_loop_threshold": 10},
    )
    assert scores[0].action == RepairAction.START_CONTAINER
    assert scores[0].score >= SAFE_AUTO_THRESHOLD


def test_action_scorer_exited_clean_with_crash_loop_escalates() -> None:
    """Exited(0) with restart_count>threshold → ESCALATE only."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions(
        "Exited(0)",
        {"restart_count": 15, "crash_loop_threshold": 10},
    )
    assert scores[0].action == RepairAction.ESCALATE


def test_action_scorer_exited_nonzero_escalates() -> None:
    """Exited(non-zero) → ESCALATE has highest blast_radius and confidence (will be decision in engine)."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("Exited(1)", {"restart_count": 0})
    # ESCALATE option is available; highest confidence is ESCALATE (0.85 vs 0.05)
    escalate_score = next((s for s in scores if s.action == RepairAction.ESCALATE), None)
    assert escalate_score is not None
    assert escalate_score.confidence == 0.85


def test_action_scorer_crash_loop_escalates() -> None:
    """crash-loop reason → ESCALATE has highest confidence."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("crash-loop", {})
    escalate_score = next((s for s in scores if s.action == RepairAction.ESCALATE), None)
    assert escalate_score is not None
    assert escalate_score.confidence == 0.95


def test_action_scorer_unknown_reason_escalates() -> None:
    """Unknown reason → ESCALATE option available (conservative default)."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("UNKNOWN_ERROR", {})
    escalate_score = next((s for s in scores if s.action == RepairAction.ESCALATE), None)
    assert escalate_score is not None
    assert escalate_score.confidence == 0.3


def test_action_scorer_returns_sorted_by_score() -> None:
    """Scores returned sorted by score descending."""
    scorer = DefaultActionScorer()
    scores = scorer.score_actions("COLD_STRIKE", {})
    for i in range(len(scores) - 1):
        assert scores[i].score >= scores[i + 1].score


# ContainerStatus tests


def test_container_status_frozen_immutable() -> None:
    """ContainerStatus is frozen dataclass."""
    cs = ContainerStatus(
        name="test",
        state="running",
        exit_code=0,
        restart_count=0,
        health=None,
    )
    with pytest.raises(AttributeError):
        cs.state = "exited"  # type: ignore


# InMemoryDockerPort tests


@pytest.mark.asyncio
async def test_in_memory_docker_port_lists_containers() -> None:
    """InMemoryDockerPort.list_containers returns configured containers."""
    containers = [
        ContainerStatus(
            name="app1",
            state="running",
            exit_code=0,
            restart_count=0,
            health=None,
        ),
        ContainerStatus(
            name="app2",
            state="exited",
            exit_code=0,
            restart_count=2,
            health=None,
        ),
    ]
    port = InMemoryDockerPort(containers=containers)
    result = await port.list_containers()
    assert len(result) == 2
    assert result[0].name == "app1"
    assert result[1].name == "app2"


@pytest.mark.asyncio
async def test_in_memory_docker_port_start_container_success() -> None:
    """InMemoryDockerPort.start_container returns configured result."""
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=0,
            health=None,
        ),
    ]
    port = InMemoryDockerPort(containers=containers, start_result=True)
    result = await port.start_container("app1")
    assert result is True


@pytest.mark.asyncio
async def test_in_memory_docker_port_start_container_fails_on_crash() -> None:
    """start_container returns False if exit_code != 0 (safety check)."""
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=1,
            restart_count=0,
            health=None,
        ),
    ]
    port = InMemoryDockerPort(containers=containers, start_result=True)
    result = await port.start_container("app1")
    assert result is False


@pytest.mark.asyncio
async def test_in_memory_docker_port_start_container_fails_on_crash_loop() -> None:
    """start_container returns False if restart_count > 10 (safety check)."""
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=15,
            health=None,
        ),
    ]
    port = InMemoryDockerPort(containers=containers, start_result=True)
    result = await port.start_container("app1")
    assert result is False


@pytest.mark.asyncio
async def test_in_memory_docker_port_start_container_unknown_name() -> None:
    """start_container returns False for unknown container name."""
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=0,
            health=None,
        ),
    ]
    port = InMemoryDockerPort(containers=containers, start_result=True)
    result = await port.start_container("unknown")
    assert result is False


# RepairEngine tests


@pytest.mark.asyncio
async def test_repair_engine_warm_model_above_threshold_executes() -> None:
    """RepairEngine executes WARM_MODEL if score >= threshold."""
    scorer = DefaultActionScorer()
    # loaded dict must be populated for verification to succeed
    ollama = InMemoryOllamaPort(
        warm_result=True,
        loaded={NODE_URL: [MODEL]},
    )
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, ollama_port=ollama, ledger_port=ledger)

    action = await engine.evaluate_and_act(
        "COLD_STRIKE",
        {"node_url": NODE_URL, "model": MODEL, "warmup_fails": 0},
    )

    # Should return WARM_MODEL (auto-executed and verified)
    assert action == RepairAction.WARM_MODEL
    # Should log REPAIR_OK
    events = [e.get("event") for e in ledger.entries]
    assert "REPAIR_OK" in events


@pytest.mark.asyncio
async def test_repair_engine_below_threshold_escalates() -> None:
    """RepairEngine escalates if score < threshold."""
    scorer = DefaultActionScorer()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, ledger_port=ledger)

    action = await engine.evaluate_and_act(
        "UNKNOWN_REASON",
        {"some_context": "data"},
    )

    # Unknown reason → all actions below threshold → ESCALATE
    assert action == RepairAction.ESCALATE
    events = [e.get("event") for e in ledger.entries]
    assert "ESCALATE" in events


@pytest.mark.asyncio
async def test_repair_engine_execute_action_logs_to_ledger() -> None:
    """RepairEngine logs all actions to ledger."""
    scorer = DefaultActionScorer()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, ledger_port=ledger)

    await engine.evaluate_and_act("COLD_STRIKE", {"warmup_fails": 0})

    assert len(ledger.entries) > 0
    # Check for timestamp and event fields
    assert all("ts" in e and "event" in e for e in ledger.entries)


@pytest.mark.asyncio
async def test_repair_engine_start_container_above_threshold_executes() -> None:
    """RepairEngine executes START_CONTAINER if score >= threshold.

    Mock: container is exited(0), start succeeds, verify sees running state.
    """
    scorer = DefaultActionScorer()

    # Create a stateful docker port mock
    class StatefulDockerPort:
        def __init__(self):
            self.state = "exited"

        async def list_containers(self):
            return [
                ContainerStatus(
                    name="app1",
                    state=self.state,
                    exit_code=0,
                    restart_count=5,
                    health=None,
                ),
            ]

        async def start_container(self, name: str) -> bool:
            if name == "app1" and self.state == "exited":
                self.state = "running"
                return True
            return False

    docker = StatefulDockerPort()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, docker_port=docker, ledger_port=ledger)

    action = await engine.evaluate_and_act(
        "Exited(0)",
        {"container_name": "app1", "restart_count": 5, "crash_loop_threshold": 10},
    )

    # Should execute START_CONTAINER and verify it
    assert action == RepairAction.START_CONTAINER
    events = [e.get("event") for e in ledger.entries]
    assert "REPAIR_OK" in events


# Watchdog integration with docker


@pytest.mark.asyncio
async def test_watchdog_run_once_docker_detects_exited_clean() -> None:
    """Watchdog.run_once_docker detects exited-clean containers."""
    cfg = _cfg()
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=0,
            health=None,
        ),
    ]
    docker = InMemoryDockerPort(containers=containers, start_result=True)
    scorer = DefaultActionScorer()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, docker_port=docker, ledger_port=ledger)
    ollama = InMemoryOllamaPort()

    watchdog = Watchdog(cfg, ollama, ledger, repair_engine=engine, docker_port=docker)
    await watchdog.run_once_docker()

    # Should have logged repair attempt
    assert len(ledger.entries) > 0


@pytest.mark.asyncio
async def test_watchdog_run_once_docker_detects_crash_loop() -> None:
    """Watchdog.run_once_docker detects crash-loop containers."""
    cfg = _cfg()
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=15,
            health=None,
        ),
    ]
    docker = InMemoryDockerPort(containers=containers)
    scorer = DefaultActionScorer()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, docker_port=docker, ledger_port=ledger)
    ollama = InMemoryOllamaPort()

    watchdog = Watchdog(cfg, ollama, ledger, repair_engine=engine, docker_port=docker)
    await watchdog.run_once_docker()

    # Should have escalated (crash-loop)
    events = [e.get("event") for e in ledger.entries]
    assert "ESCALATE" in events


@pytest.mark.asyncio
async def test_watchdog_run_once_docker_ignores_healthy() -> None:
    """Watchdog.run_once_docker ignores healthy running containers."""
    cfg = _cfg()
    containers = [
        ContainerStatus(
            name="app1",
            state="running",
            exit_code=0,
            restart_count=0,
            health="healthy",
        ),
    ]
    docker = InMemoryDockerPort(containers=containers)
    scorer = DefaultActionScorer()
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, docker_port=docker, ledger_port=ledger)
    ollama = InMemoryOllamaPort()

    watchdog = Watchdog(cfg, ollama, ledger, repair_engine=engine, docker_port=docker)
    await watchdog.run_once_docker()

    # Should not log anything for healthy containers
    assert len(ledger.entries) == 0


# Comprehensive end-to-end scenarios


@pytest.mark.asyncio
async def test_end_to_end_cold_strike_warm_and_recover() -> None:
    """End-to-end: COLD_STRIKE → WARM_MODEL → recovery verified → REPAIR_OK."""
    scorer = DefaultActionScorer()
    ollama = InMemoryOllamaPort(warm_result=True, loaded={NODE_URL: [MODEL]})
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, ollama_port=ollama, ledger_port=ledger)

    action = await engine.evaluate_and_act(
        "COLD_STRIKE",
        {"node_url": NODE_URL, "model": MODEL, "warmup_fails": 0},
    )

    assert action == RepairAction.WARM_MODEL
    assert any(e.get("event") == "REPAIR_OK" for e in ledger.entries)


@pytest.mark.asyncio
async def test_end_to_end_container_restart_and_verify() -> None:
    """End-to-end: Exited(0) → START_CONTAINER → verify running → REPAIR_OK."""
    scorer = DefaultActionScorer()
    containers = [
        ContainerStatus(
            name="app1",
            state="exited",
            exit_code=0,
            restart_count=0,
            health=None,
        ),
    ]
    docker = InMemoryDockerPort(containers=containers, start_result=True)
    ledger = InMemoryLedger()
    engine = RepairEngine(scorer=scorer, docker_port=docker, ledger_port=ledger)

    # After start, update container state
    docker.update_containers(
        [
            ContainerStatus(
                name="app1",
                state="running",
                exit_code=0,
                restart_count=0,
                health=None,
            ),
        ]
    )

    action = await engine.evaluate_and_act(
        "Exited(0)",
        {"container_name": "app1", "restart_count": 0, "crash_loop_threshold": 10},
    )

    assert action == RepairAction.START_CONTAINER
    assert any(e.get("event") == "REPAIR_OK" for e in ledger.entries)
