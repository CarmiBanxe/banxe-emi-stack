"""Sprint 2 Watchdog MVP — skeleton tests (>=8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.watchdog.watchdog import (
    EfficiencyMetrics,
    InMemoryLedger,
    InMemoryOllamaPort,
    NodeConfig,
    NodeMonitor,
    NodeState,
    Watchdog,
    WatchdogConfig,
)

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


def _monitor(
    ollama: InMemoryOllamaPort | None = None,
    ledger: InMemoryLedger | None = None,
    **cfg_kwargs: object,
) -> tuple[NodeMonitor, InMemoryLedger]:
    cfg = _cfg(**cfg_kwargs)
    led = ledger or InMemoryLedger()
    port = ollama or InMemoryOllamaPort(loaded={NODE_URL: [MODEL]})
    mon = NodeMonitor(config=cfg, node=cfg.nodes[0], ollama=port, ledger=led)
    return mon, led


@pytest.mark.asyncio
async def test_p1_healthy_when_model_loaded() -> None:
    mon, _ = _monitor()
    state = await mon.p1_health()
    assert state == NodeState.HEALTHY


@pytest.mark.asyncio
async def test_p1_cold_strike_accumulates_when_model_absent() -> None:
    port = InMemoryOllamaPort(loaded={NODE_URL: []})
    mon, led = _monitor(ollama=port, cold_strikes=3)
    await mon.p1_health()
    assert mon._cold_strikes == 1
    assert any(e["event"] == "COLD_STRIKE" for e in led.entries)


@pytest.mark.asyncio
async def test_p1_triggers_warm_after_cold_strike_threshold() -> None:
    port = InMemoryOllamaPort(loaded={NODE_URL: []}, warm_result=True)
    mon, led = _monitor(ollama=port, cold_strikes=1)
    await mon.p1_health()
    assert any(e["event"] == "WARMING" for e in led.entries)
    assert any(e["event"] == "WARM_OK" for e in led.entries)


@pytest.mark.asyncio
async def test_p1_unreachable_on_exception() -> None:
    class FailPort(InMemoryOllamaPort):
        async def list_models(self, node_url: str, timeout: float) -> list[str]:
            raise ConnectionError("refused")

    mon, led = _monitor(ollama=FailPort())
    state = await mon.p1_health()
    assert state == NodeState.UNREACHABLE
    assert any(e["event"] == "UNREACHABLE" for e in led.entries)


@pytest.mark.asyncio
async def test_p2_efficiency_healthy_returns_metrics() -> None:
    mon, _ = _monitor()
    metrics = await mon.p2_efficiency(MODEL)
    assert metrics is not None
    assert isinstance(metrics, EfficiencyMetrics)
    assert metrics.correctness is True
    assert metrics.tokens_per_sec > 0


@pytest.mark.asyncio
async def test_p2_slow_escalates_when_tps_below_threshold() -> None:
    gen = {
        "response": "4",
        "eval_count": 1,
        "eval_duration": int(1.0 * 1e9),
        "total_duration": int(1.1 * 1e9),
        "load_duration": 0,
    }
    port = InMemoryOllamaPort(loaded={NODE_URL: [MODEL]}, gen_response=gen)
    mon, led = _monitor(ollama=port)
    await mon.p2_efficiency(MODEL)
    assert mon.state == NodeState.SLOW
    assert any(e["event"] == "ESCALATE" for e in led.entries)


@pytest.mark.asyncio
async def test_p2_incorrect_escalates_when_response_wrong() -> None:
    gen = {
        "response": "banana",
        "eval_count": 10,
        "eval_duration": int(0.5 * 1e9),
        "total_duration": int(0.6 * 1e9),
        "load_duration": 0,
    }
    port = InMemoryOllamaPort(loaded={NODE_URL: [MODEL]}, gen_response=gen)
    mon, led = _monitor(ollama=port)
    await mon.p2_efficiency(MODEL)
    # Single wrong response triggers DEGRADED_SUCCESS_RATE before INCORRECT check
    assert mon.state == NodeState.DEGRADED
    assert any(e.get("reason") == "DEGRADED_SUCCESS_RATE" for e in led.entries)


@pytest.mark.asyncio
async def test_p2_logs_efficiency_entry_with_required_fields() -> None:
    mon, led = _monitor()
    await mon.p2_efficiency(MODEL)
    eff = [e for e in led.entries if e.get("event") == "EFFICIENCY"]
    assert len(eff) == 1
    assert "tokens_per_sec" in eff[0]
    assert "hot_latency_s" in eff[0]
    assert "success_rate" in eff[0]
    assert "correctness" in eff[0]


@pytest.mark.asyncio
async def test_escalation_cooldown_prevents_duplicate_alerts() -> None:
    gen = {
        "response": "banana",
        "eval_count": 10,
        "eval_duration": int(0.5 * 1e9),
        "total_duration": int(0.6 * 1e9),
        "load_duration": 0,
    }
    port = InMemoryOllamaPort(loaded={NODE_URL: [MODEL]}, gen_response=gen)
    mon, led = _monitor(ollama=port, escalation_cooldown_s=9999)
    await mon.p2_efficiency(MODEL)
    await mon.p2_efficiency(MODEL)
    escalations = [e for e in led.entries if e.get("event") == "ESCALATE"]
    assert len(escalations) == 1


@pytest.mark.asyncio
async def test_warmup_fail_escalates_after_threshold() -> None:
    port = InMemoryOllamaPort(loaded={NODE_URL: []}, warm_result=False)
    mon, led = _monitor(ollama=port, cold_strikes=1, escalate_after_warmup_fails=2)
    await mon.p1_health()
    mon._cold_strikes = 0
    await mon.p1_health()
    assert any(e.get("reason") == "WARM_EXHAUSTED" for e in led.entries)


@pytest.mark.asyncio
async def test_watchdog_run_once_p1_returns_states_for_all_nodes() -> None:
    port = InMemoryOllamaPort(loaded={NODE_URL: [MODEL]})
    cfg = _cfg()
    led = InMemoryLedger()
    wd = Watchdog(cfg, port, led)
    states = await wd.run_once_p1()
    assert len(states) == len(cfg.nodes)
    assert all(isinstance(s, NodeState) for s in states)
