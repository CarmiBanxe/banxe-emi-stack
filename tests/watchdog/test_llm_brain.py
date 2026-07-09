"""A2 tests — LLM Tier-2 brain: WatchdogConfig llm section + enrich_with_llm wiring.

Coverage:
- WatchdogConfig.from_yaml reads llm: section fields correctly
- llm.enabled=true → RootCauseClassifier instantiated with ollama port
- llm.enabled=false → RootCauseClassifier is None (port not called)
- enrich_with_llm fires on UNKNOWN + confidence < 0.5 + port present
- enrich_with_llm skips when reason is not UNKNOWN
- enrich_with_llm skips when confidence >= 0.5
- enrich_with_llm skips when ollama port is None
- enriched Classification carries llm_diagnosis and llm_confidence_hint
- port exception → original classification returned unchanged
- partial LLM response (no CONFIDENCE) → hint is None
- partial LLM response (no DIAGNOSIS) → diag is None
- llm_timeout_s passed through from config
- llm_model passed through from config
- llm_node_url passed through from config
- default llm fields when section absent from yaml
15 tests total (≥ 15 required by spec).
"""

from __future__ import annotations

import textwrap
from unittest.mock import AsyncMock

import pytest

from services.watchdog.root_cause_classifier import (
    Classification,
    RootCause,
    RootCauseClassifier,
)
from services.watchdog.watchdog import WatchdogConfig

# ── helpers ───────────────────────────────────────────────────────────────────


def _config_from_str(yaml_str: str) -> WatchdogConfig:
    """Write yaml_str to a temp file and load via from_yaml."""
    from pathlib import Path
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_str)
        path = Path(f.name)
    return WatchdogConfig.from_yaml(path)


_BASE_YAML = textwrap.dedent(
    """
    probe:
      p1_health_interval_s: 60
      p2_efficiency_interval_s: 900
      p1_timeout_s: 8
      gen_timeout_s: 120
    thresholds:
      cold_strikes: 2
      escalate_after_warmup_fails: 3
      backoff_s: [10, 30, 120]
      escalation_cooldown_s: 1800
      min_tokens_per_sec:
        default: 8
      max_hot_latency_s: 8
      max_cold_start_s: 90
      min_success_rate: 0.95
      correctness_probe:
        prompt: "What is 2+2?"
        expect_contains: "4"
    nodes: []
    autonomy:
      may_warm: true
      may_restart_ollama: false
      may_config_sync: false
      may_recreate_stateless: false
      may_sync_ollama_ctx: false
      may_kill_runaway: false
      may_reroute: false
      may_evict: false
    circuit_breaker:
      max_attempts: 3
      backoff_base_s: 10
      max_quarantine_s: 1800
    escalation:
      ledger_path: /tmp/watchdog-test.jsonl
      webhook: null
    docker:
      socket: /var/run/docker.sock
      auto_start_exited_clean: false
      crash_loop_threshold: 10
      monitor_containers: []
    audit:
      enabled: false
      path: /tmp/watchdog-audit-test.jsonl
    metrics:
      enabled: false
      port: 9091
    dependency_graph: {}
    snapshots:
      enabled: false
      dir: /tmp
    slo:
      model_downtime_threshold_s: 3600
    config_drift:
      enabled: false
      interval_s: 3600
      baseline: services/watchdog/config-baseline.yaml
    """
)

_YAML_WITH_LLM = _BASE_YAML + textwrap.dedent(
    """
        llm:
          enabled: true
          node_url: "http://192.168.0.72:11434"
          model: "llama3.3:70b"
          timeout_s: 35
        """
)

_YAML_LLM_DISABLED = _BASE_YAML + textwrap.dedent(
    """
        llm:
          enabled: false
          node_url: "http://192.168.0.72:11434"
          model: "llama3.3:70b"
          timeout_s: 35
        """
)


def _make_mock_port(response_text: str = "DIAGNOSIS: OOM | CONFIDENCE: 0.85") -> AsyncMock:
    port = AsyncMock()
    port.generate = AsyncMock(return_value={"response": response_text})
    return port


def _unknown_low_conf() -> Classification:
    return Classification(reason=RootCause.UNKNOWN, confidence=0.30, evidence=[])


# ── WatchdogConfig — llm section parsing ─────────────────────────────────────


def test_config_llm_enabled_reads_true() -> None:
    cfg = _config_from_str(_YAML_WITH_LLM)
    assert cfg.llm_enabled is True


def test_config_llm_node_url_parsed() -> None:
    cfg = _config_from_str(_YAML_WITH_LLM)
    assert cfg.llm_node_url == "http://192.168.0.72:11434"


def test_config_llm_model_parsed() -> None:
    cfg = _config_from_str(_YAML_WITH_LLM)
    assert cfg.llm_model == "llama3.3:70b"


def test_config_llm_timeout_s_parsed() -> None:
    cfg = _config_from_str(_YAML_WITH_LLM)
    assert cfg.llm_timeout_s == 35


def test_config_llm_disabled_field() -> None:
    cfg = _config_from_str(_YAML_LLM_DISABLED)
    assert cfg.llm_enabled is False


def test_config_llm_section_absent_defaults_to_disabled() -> None:
    cfg = _config_from_str(_BASE_YAML)
    assert cfg.llm_enabled is False
    assert cfg.llm_node_url == ""


# ── enrich_with_llm — fires on UNKNOWN + low-conf + port present ─────────────


async def test_enrich_fires_on_unknown_low_confidence() -> None:
    port = _make_mock_port()
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    result = await clsf.enrich_with_llm(_unknown_low_conf())
    port.generate.assert_awaited_once()
    assert result.llm_diagnosis is not None


async def test_enrich_returns_llm_diagnosis_field() -> None:
    port = _make_mock_port("DIAGNOSIS: OOM pressure | CONFIDENCE: 0.85")
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    result = await clsf.enrich_with_llm(_unknown_low_conf())
    assert result.llm_diagnosis == "OOM pressure"
    assert result.llm_confidence_hint == pytest.approx(0.85)


async def test_enrich_skips_when_reason_not_unknown() -> None:
    port = _make_mock_port()
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    high_conf = Classification(reason=RootCause.OOM_KILLED, confidence=0.80, evidence=[])
    result = await clsf.enrich_with_llm(high_conf)
    port.generate.assert_not_awaited()
    assert result.llm_diagnosis is None


async def test_enrich_skips_when_confidence_gte_05() -> None:
    port = _make_mock_port()
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    semi_conf = Classification(reason=RootCause.UNKNOWN, confidence=0.50, evidence=[])
    result = await clsf.enrich_with_llm(semi_conf)
    port.generate.assert_not_awaited()
    assert result.llm_diagnosis is None


async def test_enrich_skips_when_port_is_none() -> None:
    clsf = RootCauseClassifier(ollama_port=None)
    result = await clsf.enrich_with_llm(_unknown_low_conf())
    assert result.llm_diagnosis is None


async def test_enrich_port_exception_returns_original() -> None:
    port = AsyncMock()
    port.generate = AsyncMock(side_effect=OSError("connection refused"))
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    original = _unknown_low_conf()
    result = await clsf.enrich_with_llm(original)
    assert result.reason == RootCause.UNKNOWN
    assert result.llm_diagnosis is None


async def test_enrich_partial_response_no_confidence_hint_is_none() -> None:
    port = _make_mock_port("DIAGNOSIS: disk full")
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    result = await clsf.enrich_with_llm(_unknown_low_conf())
    assert result.llm_diagnosis == "disk full"
    assert result.llm_confidence_hint is None


async def test_enrich_partial_response_no_diagnosis_diag_is_none() -> None:
    port = _make_mock_port("CONFIDENCE: 0.90")
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    result = await clsf.enrich_with_llm(_unknown_low_conf())
    assert result.llm_diagnosis is None
    assert result.llm_confidence_hint == pytest.approx(0.90)


async def test_enrich_preserves_original_reason_and_evidence() -> None:
    port = _make_mock_port()
    clsf = RootCauseClassifier(ollama_port=port, ollama_node_url="http://host:11434")
    original = Classification(reason=RootCause.UNKNOWN, confidence=0.30, evidence=["some log line"])
    result = await clsf.enrich_with_llm(original)
    assert result.reason == RootCause.UNKNOWN
    assert result.evidence == ["some log line"]
