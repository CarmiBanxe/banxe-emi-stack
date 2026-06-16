"""Factory selection tests for S16.7 — real-API reader / in-memory / auto."""

from __future__ import annotations

import pytest

from services.ci_governance.factory import (
    get_protection_reader,
    get_real_gh_protection_reader,
    resolve_gh_token,
)
from services.ci_governance.gh_api_protection_reader import (
    GitHubApiProtectionReader,
)
from services.ci_governance.in_memory_protection_reader import (
    InMemoryProtectionReader,
)

_TOKEN_ENVS = ("CI_GOVERNANCE_GH_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


@pytest.fixture(autouse=True)
def _clear_caches_and_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test starts with a clean factory cache + no token env."""
    for k in _TOKEN_ENVS:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("CI_GOVERNANCE_READER_MODE", raising=False)
    monkeypatch.delenv("CI_GOVERNANCE_REPO_OWNER", raising=False)
    monkeypatch.delenv("CI_GOVERNANCE_REPO_NAME", raising=False)
    monkeypatch.delenv("CI_GOVERNANCE_BRANCH", raising=False)
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()
    yield
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()


def test_factory_in_memory_when_READER_MODE_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "in_memory")
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    reader = get_protection_reader()
    assert isinstance(reader, InMemoryProtectionReader)


def test_factory_gh_api_when_READER_MODE_gh_api_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "gh_api")
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    reader = get_protection_reader()
    assert isinstance(reader, GitHubApiProtectionReader)


def test_factory_gh_api_when_READER_MODE_auto_with_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "auto")
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    reader = get_protection_reader()
    assert isinstance(reader, GitHubApiProtectionReader)


def test_factory_in_memory_when_READER_MODE_auto_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "auto")
    # All three token vars left unset by the autouse fixture.
    reader = get_protection_reader()
    assert isinstance(reader, InMemoryProtectionReader)


def test_factory_uses_CI_GOVERNANCE_GH_TOKEN_first_then_GH_TOKEN_then_GITHUB_TOKEN(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only GITHUB_TOKEN set → picked.
    monkeypatch.setenv("GITHUB_TOKEN", "github-token-z")
    assert resolve_gh_token() == "github-token-z"

    # GH_TOKEN overrides GITHUB_TOKEN.
    monkeypatch.setenv("GH_TOKEN", "gh-token-y")
    assert resolve_gh_token() == "gh-token-y"

    # CI_GOVERNANCE_GH_TOKEN overrides both.
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "ci-token-x")
    assert resolve_gh_token() == "ci-token-x"

    # Empty CI_GOVERNANCE_GH_TOKEN falls through to GH_TOKEN.
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "")
    assert resolve_gh_token() == "gh-token-y"


def test_factory_lru_cache_clear_resets_between_tests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After cache_clear, env changes are honoured by the next call."""
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "in_memory")
    first = get_protection_reader()
    assert isinstance(first, InMemoryProtectionReader)

    # Flip env then cache_clear — next call must reflect new env.
    monkeypatch.setenv("CI_GOVERNANCE_READER_MODE", "gh_api")
    monkeypatch.setenv("CI_GOVERNANCE_GH_TOKEN", "tok-x")
    get_protection_reader.cache_clear()
    get_real_gh_protection_reader.cache_clear()
    second = get_protection_reader()
    assert isinstance(second, GitHubApiProtectionReader)
    # And without cache_clear, the result is stable (singleton).
    third = get_protection_reader()
    assert second is third
