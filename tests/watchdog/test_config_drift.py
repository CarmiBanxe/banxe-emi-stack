"""GAP-C tests — ConfigDriftDetector + Watchdog.run_once_config_drift integration."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from services.watchdog.audit_log import InMemoryAuditLog
from services.watchdog.config_drift import (
    EVENT_CONFIG_DRIFT,
    CompositeRuntimeConfigReader,
    ConfigDriftDetector,
    FileBasedOllamaConfigReader,
    InMemoryRuntimeConfigReader,
    _hash_value,
    _is_sensitive_key,
)
from services.watchdog.watchdog import (
    InMemoryLedger,
    InMemoryOllamaPort,
    Watchdog,
    WatchdogConfig,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_baseline(tmp_path: Path, config: dict) -> Path:
    baseline = tmp_path / "config-baseline.yaml"
    baseline.write_text(yaml.dump({"config": config}), encoding="utf-8")
    return baseline


def _cfg(**kwargs) -> WatchdogConfig:
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


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_is_sensitive_key_detects_password():
    assert _is_sensitive_key("POSTGRES_PASSWORD") is True
    assert _is_sensitive_key("my_secret") is True
    assert _is_sensitive_key("api_token") is True
    assert _is_sensitive_key("POSTGRES_DB") is False
    assert _is_sensitive_key("OLLAMA_NUM_CTX") is False


def test_hash_value_returns_prefix_and_never_raw():
    raw = "supersecret"
    h = _hash_value(raw)
    assert h.startswith("sha256:")
    assert raw not in h
    assert len(h) == len("sha256:") + 16


# ---------------------------------------------------------------------------
# ConfigDriftDetector — core scenarios
# ---------------------------------------------------------------------------


def test_no_drift_when_live_matches_baseline(tmp_path: Path):
    baseline = _write_baseline(tmp_path, {"evo1.OLLAMA_NUM_CTX": "8192"})
    reader = InMemoryRuntimeConfigReader({"evo1.OLLAMA_NUM_CTX": "8192"})
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert result.drift_detected is False
    assert result.strict_differs is False
    assert result.strict_weakened is False
    assert result.summary == "no drift"


def test_drift_detected_missing_baseline_key(tmp_path: Path):
    baseline = _write_baseline(
        tmp_path, {"evo1.OLLAMA_NUM_CTX": "8192", "evo2.OLLAMA_NUM_CTX": "8192"}
    )
    reader = InMemoryRuntimeConfigReader({"evo1.OLLAMA_NUM_CTX": "8192"})
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert result.drift_detected is True
    assert "evo2.OLLAMA_NUM_CTX" in result.missing_contexts


def test_drift_detected_extra_live_key(tmp_path: Path):
    baseline = _write_baseline(tmp_path, {"evo1.OLLAMA_NUM_CTX": "8192"})
    reader = InMemoryRuntimeConfigReader(
        {"evo1.OLLAMA_NUM_CTX": "8192", "evo2.OLLAMA_NUM_CTX": "131072"}
    )
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert result.drift_detected is True
    assert "evo2.OLLAMA_NUM_CTX" in result.extra_contexts


def test_value_mismatch_non_secret_sets_strict_differs(tmp_path: Path):
    """Ollama context window changed: strict_differs=True, strict_weakened=False."""
    baseline = _write_baseline(tmp_path, {"evo2.OLLAMA_NUM_CTX": "8192"})
    reader = InMemoryRuntimeConfigReader({"evo2.OLLAMA_NUM_CTX": "131072"})
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert result.drift_detected is True
    assert result.strict_differs is True
    assert result.strict_weakened is False
    assert "evo2.OLLAMA_NUM_CTX" in result.missing_contexts


def test_secret_hash_mismatch_sets_strict_weakened(tmp_path: Path):
    """Password hash mismatch → CRITICAL path (strict_weakened=True)."""
    expected_hash = _hash_value("correct_password")
    wrong_hash = _hash_value("wrong_password")
    baseline = _write_baseline(tmp_path, {"pg.POSTGRES_PASSWORD": expected_hash})
    reader = InMemoryRuntimeConfigReader({"pg.POSTGRES_PASSWORD": wrong_hash})
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert result.drift_detected is True
    assert result.strict_weakened is True
    assert result.strict_differs is True


def test_raw_secret_never_appears_in_summary(tmp_path: Path):
    """Raw secret value must NEVER appear in the DriftResult summary."""
    raw_secret = "my_super_secret_password_xyz"
    expected_hash = _hash_value(raw_secret)
    wrong_hash = _hash_value("another_password")
    baseline = _write_baseline(tmp_path, {"pg.POSTGRES_PASSWORD": expected_hash})
    reader = InMemoryRuntimeConfigReader({"pg.POSTGRES_PASSWORD": wrong_hash})
    det = ConfigDriftDetector(reader, baseline)
    result = det.detect()
    assert raw_secret not in result.summary
    assert raw_secret not in str(result.missing_contexts)
    assert raw_secret not in str(result.extra_contexts)


def test_missing_baseline_file_raises(tmp_path: Path):
    reader = InMemoryRuntimeConfigReader({})
    det = ConfigDriftDetector(reader, tmp_path / "nonexistent.yaml")
    with pytest.raises(FileNotFoundError):
        det.detect()


# ---------------------------------------------------------------------------
# FileBasedOllamaConfigReader
# ---------------------------------------------------------------------------


def test_file_based_ollama_reader_parses_conf(tmp_path: Path):
    conf = tmp_path / "override.conf"
    conf.write_text("OLLAMA_NUM_CTX=131072\n# comment\nOLLAMA_KEEP_ALIVE=5m\n", encoding="utf-8")
    reader = FileBasedOllamaConfigReader({"evo2": conf})
    live = reader.read_live_config()
    assert live["evo2.OLLAMA_NUM_CTX"] == "131072"
    assert live["evo2.OLLAMA_KEEP_ALIVE"] == "5m"


def test_file_based_ollama_reader_missing_file_returns_empty(tmp_path: Path):
    reader = FileBasedOllamaConfigReader({"evo1": tmp_path / "missing.conf"})
    assert reader.read_live_config() == {}


def test_file_based_ollama_reader_hashes_sensitive_keys(tmp_path: Path):
    conf = tmp_path / "override.conf"
    conf.write_text("MY_SECRET_TOKEN=rawvalue\n", encoding="utf-8")
    reader = FileBasedOllamaConfigReader({"node1": conf})
    live = reader.read_live_config()
    val = live["node1.MY_SECRET_TOKEN"]
    assert val.startswith("sha256:")
    assert "rawvalue" not in val


# ---------------------------------------------------------------------------
# CompositeRuntimeConfigReader
# ---------------------------------------------------------------------------


def test_composite_reader_merges_and_later_wins():
    r1 = InMemoryRuntimeConfigReader({"a": "1", "b": "2"})
    r2 = InMemoryRuntimeConfigReader({"b": "override", "c": "3"})
    comp = CompositeRuntimeConfigReader([r1, r2])
    live = comp.read_live_config()
    assert live == {"a": "1", "b": "override", "c": "3"}


# ---------------------------------------------------------------------------
# Watchdog integration: run_once_config_drift
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_once_config_drift_audit_record_on_drift(tmp_path: Path):
    baseline = _write_baseline(tmp_path, {"evo2.OLLAMA_NUM_CTX": "8192"})
    reader = InMemoryRuntimeConfigReader({"evo2.OLLAMA_NUM_CTX": "131072"})
    detector = ConfigDriftDetector(reader, baseline)

    audit = InMemoryAuditLog()
    wd = Watchdog(
        config=_cfg(),
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
        audit_log=audit,
        config_drift_detector=detector,
    )

    result = await wd.run_once_config_drift()
    assert result is not None
    assert result.drift_detected is True
    assert len(audit.records) == 1
    rec = audit.records[0]
    assert rec.observed_state == EVENT_CONFIG_DRIFT
    assert rec.selected_action == "ESCALATE"
    assert rec.autonomy_mode == "HITL"
    assert rec.executed is False
    assert rec.manual_only is True


@pytest.mark.asyncio
async def test_run_once_config_drift_no_audit_when_clean(tmp_path: Path):
    baseline = _write_baseline(tmp_path, {"evo1.OLLAMA_NUM_CTX": "8192"})
    reader = InMemoryRuntimeConfigReader({"evo1.OLLAMA_NUM_CTX": "8192"})
    detector = ConfigDriftDetector(reader, baseline)

    audit = InMemoryAuditLog()
    wd = Watchdog(
        config=_cfg(),
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
        audit_log=audit,
        config_drift_detector=detector,
    )

    result = await wd.run_once_config_drift()
    assert result is not None
    assert result.drift_detected is False
    assert len(audit.records) == 0


@pytest.mark.asyncio
async def test_run_once_config_drift_returns_none_when_no_detector():
    wd = Watchdog(
        config=_cfg(),
        ollama=InMemoryOllamaPort(),
        ledger=InMemoryLedger(),
    )
    result = await wd.run_once_config_drift()
    assert result is None
