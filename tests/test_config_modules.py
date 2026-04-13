"""
tests/test_config_modules.py — Config module import + unit tests
S14-03 | banxe-emi-stack

Covers:
  - services/experiment_copilot/config.py (0% → ≥90%)
  - services/compliance_kb/config.py (0% → ≥90%)
  - services/aml/__init__.py (46% → ≥80%)

These are small config files with env-var driven defaults.
"""

from __future__ import annotations

# ── experiment_copilot/config.py ──────────────────────────────────────────────


def test_experiment_config_defaults():
    from services.experiment_copilot.config import ExperimentConfig

    cfg = ExperimentConfig()
    assert cfg.experiments_dir == "compliance-experiments"
    assert cfg.baselines_path == "config/aml_baselines.yaml"
    assert cfg.github_repo == "CarmiBanxe/banxe-emi-stack"
    assert cfg.clickhouse_port == 9000
    assert cfg.clickhouse_db == "banxe"


def test_experiment_config_env_override(monkeypatch):
    monkeypatch.setenv("EXPERIMENTS_DIR", "/custom/experiments")
    monkeypatch.setenv("CLICKHOUSE_PORT", "9001")

    from importlib import reload

    import services.experiment_copilot.config as mod

    reload(mod)
    cfg = mod.ExperimentConfig()
    assert cfg.experiments_dir == "/custom/experiments"
    assert cfg.clickhouse_port == 9001
    # restore
    reload(mod)


def test_experiment_config_singleton_exists():
    from services.experiment_copilot.config import config

    assert config is not None
    assert hasattr(config, "github_repo")


def test_experiment_config_github_token_default():
    from services.experiment_copilot.config import ExperimentConfig

    cfg = ExperimentConfig()
    assert isinstance(cfg.github_token, str)


def test_experiment_config_kb_api_url_default():
    from services.experiment_copilot.config import ExperimentConfig

    cfg = ExperimentConfig()
    assert "localhost" in cfg.kb_api_url or "http" in cfg.kb_api_url


# ── compliance_kb/config.py ───────────────────────────────────────────────────


def test_kb_config_defaults():
    from services.compliance_kb.config import KBConfig

    cfg = KBConfig()
    assert "chroma" in cfg.chroma_persist_dir.lower()
    assert cfg.embedding_model == "all-MiniLM-L6-v2"
    assert cfg.api_port == 8098
    assert cfg.max_results == 10
    assert 0 < cfg.similarity_threshold < 1


def test_kb_config_env_override(monkeypatch):
    monkeypatch.setenv("KB_API_PORT", "9000")
    monkeypatch.setenv("KB_MAX_RESULTS", "25")
    monkeypatch.setenv("KB_SIMILARITY_THRESHOLD", "0.9")

    from services.compliance_kb.config import KBConfig

    cfg = KBConfig()
    assert cfg.api_port == 9000
    assert cfg.max_results == 25
    assert abs(cfg.similarity_threshold - 0.9) < 0.001


def test_kb_config_singleton_exists():
    from services.compliance_kb.config import config

    assert config is not None
    assert hasattr(config, "embedding_model")


def test_kb_config_embedding_model_str():
    from services.compliance_kb.config import KBConfig

    cfg = KBConfig()
    assert isinstance(cfg.embedding_model, str)
    assert len(cfg.embedding_model) > 0


# ── services/aml/__init__.py ──────────────────────────────────────────────────


def test_aml_get_compliance_context_no_rag():
    """get_compliance_context returns empty string when RAG not available."""
    from services.aml import _RAG_AVAILABLE, get_compliance_context

    if not _RAG_AVAILABLE:
        result = get_compliance_context("SAR filing requirements")
        assert result == ""


def test_aml_get_compliance_context_with_agent_name():
    from services.aml import _RAG_AVAILABLE, get_compliance_context

    if not _RAG_AVAILABLE:
        result = get_compliance_context("SAR requirements", agent_name="banxe_aml_agent")
        assert result == ""


def test_aml_rag_available_is_bool():
    from services.aml import _RAG_AVAILABLE

    assert isinstance(_RAG_AVAILABLE, bool)


def test_aml_rag_context_k_param():
    from services.aml import _RAG_AVAILABLE, get_compliance_context

    if not _RAG_AVAILABLE:
        result = get_compliance_context("query", k=5)
        assert result == ""


# ── services/aml/aml_thresholds.py ───────────────────────────────────────────


def test_aml_thresholds_module_importable():
    from services.aml.aml_thresholds import AMLThresholdSet

    assert AMLThresholdSet is not None


def test_aml_thresholds_get_compliance_context():
    from services.aml.aml_thresholds import _RAG_AVAILABLE, get_compliance_context

    if not _RAG_AVAILABLE:
        result = get_compliance_context("AML threshold query")
        assert result == ""


def test_aml_thresholds_rag_available_is_bool():
    from services.aml.aml_thresholds import _RAG_AVAILABLE

    assert isinstance(_RAG_AVAILABLE, bool)


# ── services/notifications/sendgrid_adapter.py (import coverage) ─────────────


def test_sendgrid_adapter_module_importable():
    """Importing the module covers the module-level statements."""
    import services.notifications.sendgrid_adapter as mod

    assert hasattr(mod, "SendGridAdapter")
    assert hasattr(mod, "logger")
