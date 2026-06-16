"""Unit tests for GitHubApiProtectionReader (S16.7).

FakeHttpClient is an in-memory dict mapping URL → (status_code, body_bytes),
plus a call log capturing every (url, headers, method) tuple. No real
network; no urllib invocation; no GitHub credentials required.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from services.ci_governance.gh_api_protection_reader import (
    GitHubApiProtectionReader,
)

_EXPECTED_URL = "https://api.github.com/repos/CarmiBanxe/banxe-emi-stack/branches/main/protection"


class _FakeHttpClient:
    """Callable matching HttpClient signature (url, headers, method) → (status, bytes)."""

    def __init__(
        self,
        responses: dict[str, tuple[int, bytes]] | None = None,
    ) -> None:
        self._responses = responses or {}
        # Each entry: (url, headers_snapshot, method)
        self.calls: list[tuple[str, dict[str, str], str]] = []

    def __call__(self, url: str, headers: dict[str, str], method: str) -> tuple[int, bytes]:
        self.calls.append((url, dict(headers), method))
        return self._responses.get(url, (200, b"{}"))

    def methods_invoked(self) -> list[str]:
        return [m for _u, _h, m in self.calls]


def _provider(token: str = "test-token-abc") -> Any:
    """Build a token_provider callable that returns a fixed token."""
    return lambda: token


def _ok_body() -> bytes:
    return json.dumps(
        {
            "required_status_checks": {"strict": True, "checks": []},
            "enforce_admins": {"enabled": False},
        }
    ).encode("utf-8")


def test_reader_calls_correct_protection_url_for_owner_repo_branch() -> None:
    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider(),
        branch="main",
        http_client=client,
    )
    reader.read_main_protection()
    assert client.calls, "http_client never called"
    assert client.calls[0][0] == _EXPECTED_URL


def test_reader_sends_authorization_header_with_token() -> None:
    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider("ghp_rotating_77777"),
        http_client=client,
    )
    reader.read_main_protection()
    _url, headers, _method = client.calls[0]
    assert headers.get("Authorization") == "token ghp_rotating_77777"


def test_reader_sends_github_v3_accept_header() -> None:
    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider(),
        http_client=client,
    )
    reader.read_main_protection()
    _url, headers, _method = client.calls[0]
    assert headers.get("Accept") == "application/vnd.github.v3+json"
    # Also assert User-Agent identifies the sentry per GitHub API requirement.
    assert headers.get("User-Agent", "").startswith("banxe-ci-governance/")


def test_reader_returns_parsed_json_dict_on_200() -> None:
    payload = {
        "required_status_checks": {
            "strict": True,
            "checks": [{"context": "Smoke Gate (mock tier)"}],
        },
        "enforce_admins": {"enabled": False},
    }
    body = json.dumps(payload).encode("utf-8")
    client = _FakeHttpClient({_EXPECTED_URL: (200, body)})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider(),
        http_client=client,
    )
    out = reader.read_main_protection()
    assert isinstance(out, dict)
    assert out["required_status_checks"]["strict"] is True
    assert out["enforce_admins"] == {"enabled": False}


@pytest.mark.parametrize("status,label", [(401, "401"), (403, "403"), (404, "404"), (500, "500")])
def test_reader_raises_clear_error_with_status_in_message(status: int, label: str) -> None:
    client = _FakeHttpClient({_EXPECTED_URL: (status, b'{"message": "synthetic"}')})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider(),
        http_client=client,
    )
    with pytest.raises(RuntimeError) as exc_info:
        reader.read_main_protection()
    assert label in str(exc_info.value)


def test_reader_calls_token_provider_each_read() -> None:
    """No token caching at the adapter level — provider invoked per read."""
    invocations: list[int] = []

    def counting_provider() -> str:
        invocations.append(1)
        return "tok-N"

    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=counting_provider,
        http_client=client,
    )
    reader.read_main_protection()
    reader.read_main_protection()
    reader.read_main_protection()
    assert len(invocations) == 3


def test_reader_never_calls_mutation_methods() -> None:
    """Every recorded http_client call must use method='GET'. Also assert
    by source-text inspection that the adapter never references PUT /
    PATCH / DELETE / POST as methods."""
    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=_provider(),
        http_client=client,
    )
    for _ in range(5):
        reader.read_main_protection()
    assert all(m == "GET" for m in client.methods_invoked())
    # Defence-in-depth: source-text scan.
    src = Path(
        Path(__file__).resolve().parents[3]
        / "services"
        / "ci_governance"
        / "gh_api_protection_reader.py"
    ).read_text(encoding="utf-8")
    for forbidden in ("PUT", "PATCH", "DELETE", "POST"):
        # The string can appear in comments / error messages; assert it
        # does NOT appear as a Python-string method literal like '"POST"'.
        for needle in (f'"{forbidden}"', f"'{forbidden}'"):
            assert needle not in src, (
                f"forbidden mutation method literal {needle!r} found in gh_api_protection_reader.py"
            )


def test_reader_raises_when_token_provider_returns_empty() -> None:
    """Empty/None token must be rejected before any HTTP call goes out."""
    client = _FakeHttpClient({_EXPECTED_URL: (200, _ok_body())})
    reader = GitHubApiProtectionReader(
        owner="CarmiBanxe",
        repo="banxe-emi-stack",
        token_provider=lambda: "",  # no token
        http_client=client,
    )
    with pytest.raises(RuntimeError, match="no token"):
        reader.read_main_protection()
    assert client.calls == [], "http_client called despite missing token"
