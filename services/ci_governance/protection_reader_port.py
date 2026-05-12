"""
protection_reader_port.py — Port for reading GitHub branch-protection state
(S16.6 CI governance drift sentry).

Defines the abstract surface used by `DriftDetector` to fetch the live
protection state of `main`. Concrete adapters:

  InMemoryProtectionReader  — offline / test double; constructed with a
                              pre-built payload dict (this PR).
  GitHubAPIProtectionReader — wraps `gh api GET .../branches/main/protection`
                              with auth + retry semantics. NOT included in
                              this PR; deferred to a follow-up step that
                              requires GH_TOKEN / PAT plumbing.

The Port returns a dict that mirrors the GitHub REST API response shape:

    {
      "required_status_checks": {
        "strict": bool,
        "checks": [{"context": str, ...}, ...],
        ...
      },
      "enforce_admins": {"enabled": bool, ...} | bool,
      ...
    }

`DriftDetector` normalises the response shape before comparison; adapters
need only return the payload as the GitHub API delivers it.

Pure typing; no I/O.
"""

from __future__ import annotations

from typing import Protocol


class GitHubProtectionReaderPort(Protocol):
    """Read-only port for GitHub branch-protection state on `main`."""

    def read_main_protection(self) -> dict:
        """Return the GitHub REST API protection payload for main.

        MUST NOT mutate any remote state. MUST NOT swallow errors from the
        transport — let exceptions propagate so the caller (CLI script /
        cron wrapper) can decide whether to alert or fail silently.
        """
        ...
