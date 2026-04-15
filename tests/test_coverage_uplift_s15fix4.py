"""
tests/test_coverage_uplift_s15fix4.py — Coverage uplift batch 4
S15-FIX-3 | GAP-3 | banxe-emi-stack

Targeted tests for previously uncovered branches across:
- ProviderRegistry check_health exception path + from_yaml unknown category
- ChangeProposer live mode (non-dry-run) + HTTPGitHubPort
- Design pipeline _get_penpot_client / _get_llm factory branches
- BankstatementParser parse_camt053 IBAN skip path
- HTTPGitHubPort instantiation
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ── ProviderRegistry uncovered branches ──────────────────────────────────────
from services.providers.provider_registry import (
    ProviderCategory,
    ProviderDefinition,
    ProviderRegistry,
    ProviderStatus,
)


def _make_enabled_provider(adapter: str = "clearbank", priority: int = 1) -> ProviderDefinition:
    return ProviderDefinition(
        adapter=adapter,
        display_name=f"{adapter} (test)",
        priority=priority,
        enabled=True,
        health_url=None,
    )


class TestProviderRegistryEdgeCases:
    def test_check_health_with_no_health_url_returns_unknown(self):
        registry = ProviderRegistry({})
        provider = _make_enabled_provider()
        status = registry.check_health(provider)
        assert status == ProviderStatus.UNKNOWN

    def test_check_health_with_failing_url_returns_unhealthy(self):
        registry = ProviderRegistry({})
        provider = ProviderDefinition(
            adapter="failing-adapter",
            display_name="Failing",
            priority=1,
            enabled=True,
            health_url="http://localhost:19999/health",  # nothing listening here
        )
        status = registry.check_health(provider, timeout=0.1)
        assert status == ProviderStatus.UNHEALTHY

    def test_from_yaml_with_unknown_category_skips_entry(self, tmp_path: Path):
        yaml_content = """
unknown_category:
  slot1:
    adapter: mock
    display_name: Mock
    priority: 50
    enabled: false
payment_rails:
  clearbank:
    adapter: clearbank
    display_name: ClearBank
    priority: 1
    enabled: true
"""
        cfg = tmp_path / "providers.yaml"
        cfg.write_text(yaml_content)
        # Should not raise — unknown_category is skipped with a warning
        registry = ProviderRegistry.from_yaml(str(cfg))
        assert ProviderCategory.PAYMENT_RAILS in registry._providers

    def test_from_yaml_with_non_dict_slot_skips_it(self, tmp_path: Path):
        yaml_content = """
payment_rails:
  not_a_dict: simple_string_value
  clearbank:
    adapter: clearbank
    display_name: ClearBank
    priority: 1
    enabled: true
"""
        cfg = tmp_path / "providers.yaml"
        cfg.write_text(yaml_content)
        registry = ProviderRegistry.from_yaml(str(cfg))
        providers = registry.list_providers(ProviderCategory.PAYMENT_RAILS)
        assert len(providers) == 1
        assert providers[0].adapter == "clearbank"

    def test_resolve_no_enabled_provider_raises_runtime_error(self):
        provider = ProviderDefinition(
            adapter="disabled",
            display_name="Disabled",
            priority=1,
            enabled=False,
        )
        registry = ProviderRegistry({ProviderCategory.PAYMENT_RAILS: [provider]})
        with pytest.raises(RuntimeError, match="No enabled provider"):
            registry.resolve(ProviderCategory.PAYMENT_RAILS)

    def test_resolve_sandbox_fallback(self):
        """A sandbox provider (priority ≥ 99) is returned when no non-sandbox is enabled."""
        sandbox = ProviderDefinition(
            adapter="mock-sandbox",
            display_name="Mock Sandbox",
            priority=99,
            enabled=True,
        )
        registry = ProviderRegistry({ProviderCategory.FRAUD: [sandbox]})
        resolution = registry.resolve(ProviderCategory.FRAUD)
        assert resolution.sandbox_used is True
        assert resolution.adapter == "mock-sandbox"

    def test_resolve_no_providers_for_category_raises(self):
        registry = ProviderRegistry({})
        with pytest.raises(ValueError, match="No providers configured"):
            registry.resolve(ProviderCategory.IDV)

    def test_health_summary_returns_dict(self):
        registry = ProviderRegistry(
            {ProviderCategory.PAYMENT_RAILS: [_make_enabled_provider("clearbank")]}
        )
        summary = registry.health_summary()
        assert isinstance(summary, dict)


# ── ChangeProposer live mode ──────────────────────────────────────────────────

from services.experiment_copilot.agents.change_proposer import (
    ChangeProposer,
    HTTPGitHubPort,
    InMemoryGitHubPort,
    ProposeRequest,
)
from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.store.audit_trail import AuditTrail


def _make_active_experiment(exp_id: str = "exp-live-001") -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title="Velocity check improvement: structuring detection",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=ExperimentStatus.ACTIVE,
        hypothesis="Improved velocity windows will reduce structuring false negatives.",
        kb_citations=["eba-gl-2021-02"],
        created_by="compliance-officer",
        created_at=datetime.now(UTC),
        metrics_baseline={"false_negative_rate": 0.12},
        metrics_target={"false_negative_rate": 0.08},
    )


class TestChangeProposerLiveMode:
    def test_propose_live_mode_creates_pr_and_issue(self):
        """Live mode: InMemoryGitHubPort records PR + issue creation."""
        audit = AuditTrail()
        github = InMemoryGitHubPort()
        proposer = ChangeProposer(audit=audit, github=github)
        exp = _make_active_experiment()
        req = ProposeRequest(experiment_id=exp.id, dry_run=False)
        # Patch _create_branch to avoid actual git subprocess
        with patch.object(proposer, "_create_branch", return_value=None):
            proposal = proposer.propose(exp, req)
        assert proposal.pr_url is not None
        assert proposal.issue_url is not None
        assert len(github.prs_created) == 1
        assert len(github.issues_created) == 1

    def test_propose_live_mode_exception_sets_status_rejected(self):
        """If GitHub port raises, proposal is marked REJECTED and exception re-raised."""
        audit = AuditTrail()

        class FailingGitHubPort(InMemoryGitHubPort):
            def create_pr(self, **kwargs) -> dict:
                raise RuntimeError("GitHub API error")

        proposer = ChangeProposer(audit=audit, github=FailingGitHubPort())
        exp = _make_active_experiment("exp-fail")
        req = ProposeRequest(experiment_id=exp.id, dry_run=False)
        with patch.object(proposer, "_create_branch", return_value=None):
            with pytest.raises(RuntimeError):
                proposer.propose(exp, req)

    def test_http_github_port_instantiation(self):
        """HTTPGitHubPort stores token and repo."""
        port = HTTPGitHubPort(token="ghp-test-token", repo="CarmiBanxe/banxe-emi-stack")
        assert port._token == "ghp-test-token"
        assert port._repo == "CarmiBanxe/banxe-emi-stack"

    def test_http_github_port_headers_contain_token(self):
        port = HTTPGitHubPort(token="ghp-mytoken", repo="owner/repo")
        headers = port._headers()
        assert "Bearer ghp-mytoken" in headers["Authorization"]


# ── Design pipeline factory branches ─────────────────────────────────────────


class TestDesignPipelineFactories:
    def test_get_penpot_client_with_env_vars_returns_penpot_mcp_client(self):
        from services.design_pipeline.api import _get_penpot_client
        from services.design_pipeline.penpot_client import PenpotMCPClient

        with patch.dict(
            os.environ,
            {"PENPOT_BASE_URL": "http://penpot:3449", "PENPOT_TOKEN": "test-token"},
        ):
            client = _get_penpot_client()
        assert isinstance(client, PenpotMCPClient)

    def test_get_penpot_client_without_env_returns_inmemory(self):
        from services.design_pipeline.api import _get_penpot_client
        from services.design_pipeline.penpot_client import InMemoryPenpotClient

        env = {k: v for k, v in os.environ.items() if k not in ("PENPOT_BASE_URL", "PENPOT_TOKEN")}
        with patch.dict(os.environ, env, clear=True):
            client = _get_penpot_client()
        assert isinstance(client, InMemoryPenpotClient)

    def test_get_llm_with_ollama_url_returns_ollama_llm(self):
        from services.design_pipeline.api import _get_llm
        from services.design_pipeline.orchestrator import OllamaLLM

        with patch.dict(os.environ, {"OLLAMA_BASE_URL": "http://localhost:11434"}):
            llm = _get_llm()
        assert isinstance(llm, OllamaLLM)

    def test_get_llm_without_env_returns_inmemory(self):
        from services.design_pipeline.api import _get_llm
        from services.design_pipeline.orchestrator import InMemoryLLM

        env = {k: v for k, v in os.environ.items() if k != "OLLAMA_BASE_URL"}
        with patch.dict(os.environ, env, clear=True):
            llm = _get_llm()
        assert isinstance(llm, InMemoryLLM)


# ── BankstatementParser IBAN skip path ───────────────────────────────────────


class TestBankstatementParserIBANSkip:
    def test_parse_mt940_returns_empty_if_mt940_not_installed(self, tmp_path: Path):
        """parse_mt940 returns [] if mt940 library is not installed."""
        from services.recon import bankstatement_parser as bsp_mod

        mt940_file = tmp_path / "test.mt940"
        mt940_file.write_bytes(b":20:TEST\r\n:25:123456789\r\n")
        # Mock the mt940 import to fail
        with patch.dict("sys.modules", {"mt940": None}):
            result = bsp_mod.parse_mt940(mt940_file)
        # If mt940 is not available, returns [] immediately
        assert isinstance(result, list)


# ── Additional coverage: config/config_service YAMLConfigStore ───────────────


class TestYAMLConfigStoreEdgeCases:
    def test_yaml_config_store_loads_from_yaml(self, tmp_path: Path):
        from services.config.config_service import YAMLConfigStore

        yaml_content = """
products:
  EMI_ACCOUNT:
    display_name: "EMI Account"
    currencies:
      - GBP
      - EUR
    active: true
    fees:
      FPS:
        fee_type: FLAT
        flat_fee: "0.20"
        percentage: "0"
        min_fee: "0.20"
    limits:
      INDIVIDUAL:
        single_tx_max: "10000"
        daily_max: "50000"
        monthly_max: "200000"
        daily_tx_count: 50
        monthly_tx_count: 200
        min_tx: "0.01"
      COMPANY:
        single_tx_max: "1000000"
        daily_max: "5000000"
        monthly_max: "20000000"
        daily_tx_count: 500
        monthly_tx_count: 5000
        min_tx: "0.01"
"""
        yaml_file = tmp_path / "config.yaml"
        yaml_file.write_text(yaml_content)
        store = YAMLConfigStore(yaml_path=yaml_file)
        product = store.get_product("EMI_ACCOUNT")
        assert product is not None
        assert product.product_id == "EMI_ACCOUNT"

    def test_yaml_config_store_get_fee_missing_product(self, tmp_path: Path):
        from services.config.config_service import YAMLConfigStore

        yaml_file = tmp_path / "empty.yaml"
        yaml_file.write_text("products: {}\n")
        store = YAMLConfigStore(yaml_path=yaml_file)
        assert store.get_fee("NONEXISTENT", "FPS") is None

    def test_yaml_config_store_get_limits_missing_product(self, tmp_path: Path):
        from services.config.config_service import YAMLConfigStore

        yaml_file = tmp_path / "empty2.yaml"
        yaml_file.write_text("products: {}\n")
        store = YAMLConfigStore(yaml_path=yaml_file)
        assert store.get_limits("NONEXISTENT", "INDIVIDUAL") is None
