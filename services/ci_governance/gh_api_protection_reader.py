"""
gh_api_protection_reader.py — Real GitHub-API read-only adapter for the
S16.6 GitHubProtectionReaderPort (S16.7).

Implements `read_main_protection` against:

    GET https://api.github.com/repos/{owner}/{repo}/branches/{branch}/protection

NO mutation. NO PUT / PATCH / DELETE / POST calls. NO `urllib.request`
opener-installer. The adapter only ever passes `method="GET"` into the
injected `http_client`; the default `http_client` itself refuses any
other method.

I/O is routed through an injected callable so unit tests can supply a
FakeHttpClient that captures (url, headers, method) tuples and returns
programmed (status, body) without touching the network.

Token handling: the adapter accepts a `token_provider` callable. It is
invoked on EVERY read (no token caching at the adapter level). This lets
the factory wire env-driven resolution without the adapter holding stale
credentials in memory across rotations.

No new dependency: uses `urllib.request` from the stdlib. (`httpx` is in
requirements.txt but not needed here — read-only single-request flow.)
"""

from __future__ import annotations

from collections.abc import Callable
import json
from typing import TYPE_CHECKING
import urllib.error
import urllib.request

if TYPE_CHECKING:
    from services.ci_governance.protection_reader_port import (
        GitHubProtectionReaderPort,  # noqa: F401
    )


HttpClient = Callable[[str, dict[str, str], str], tuple[int, bytes]]
TokenProvider = Callable[[], "str | None"]

_USER_AGENT = "banxe-ci-governance/1.0"
_ACCEPT = "application/vnd.github.v3+json"


def _default_http_client(url: str, headers: dict[str, str], method: str) -> tuple[int, bytes]:
    """Stdlib default http_client. Refuses non-GET methods at this seam too —
    defence in depth so a future code change cannot escalate the adapter
    into a mutator without the type-checker AND this guard both fighting back.
    """
    if method != "GET":
        raise RuntimeError(
            f"GitHubApiProtectionReader default http_client is read-only; "
            f"refusing method={method!r}"
        )
    # B310 spirit: only allow https:// to prevent file:/ftp: scheme-shenanigans
    # even though the adapter always constructs `https://api.github.com/...`
    # itself; this guards against future code paths or test injections.
    if not url.startswith("https://"):
        raise RuntimeError(
            f"GitHubApiProtectionReader default http_client refuses non-https URL: {url!r}"
        )
    req = urllib.request.Request(url, headers=headers, method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310  # nosec B310 — https scheme guard above  # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected  # https scheme guard (nosec B310)
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class GitHubApiProtectionReader:
    """Read-only adapter for branch-protection state on GitHub."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token_provider: TokenProvider,
        branch: str = "main",
        http_client: HttpClient | None = None,
    ) -> None:
        self._owner = owner
        self._repo = repo
        self._branch = branch
        self._token_provider = token_provider
        self._http_client: HttpClient = http_client or _default_http_client

    def read_main_protection(self) -> dict:
        token = self._token_provider()
        if not token:
            raise RuntimeError(
                "GitHubApiProtectionReader: no token returned by token_provider; "
                "set CI_GOVERNANCE_GH_TOKEN / GH_TOKEN / GITHUB_TOKEN in env"
            )

        url = (
            f"https://api.github.com/repos/{self._owner}/{self._repo}"
            f"/branches/{self._branch}/protection"
        )
        headers = {
            "Authorization": f"token {token}",
            "Accept": _ACCEPT,
            "User-Agent": _USER_AGENT,
        }
        status, body = self._http_client(url, headers, "GET")
        if status == 200:
            return json.loads(body.decode("utf-8"))
        body_preview = body[:200].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"GitHubApiProtectionReader: HTTP {status} from GET {url}; body={body_preview!r}"
        )
