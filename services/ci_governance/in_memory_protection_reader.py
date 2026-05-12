"""
in_memory_protection_reader.py — Offline / test double for the
GitHubProtectionReaderPort (S16.6).

Constructed with a payload dict; `read_main_protection` returns it
verbatim. Used by:

  - Unit tests (no network, no GH_TOKEN required).
  - The CLI script's `--dry-run-payload` mode (operator pastes a payload
    captured earlier via `gh api`).
"""

from __future__ import annotations

from copy import deepcopy

from services.ci_governance.protection_reader_port import GitHubProtectionReaderPort


class InMemoryProtectionReader(GitHubProtectionReaderPort):
    """In-memory implementation of GitHubProtectionReaderPort."""

    def __init__(self, payload: dict) -> None:
        # Defensive deepcopy so callers cannot mutate the stored payload
        # via the original reference between reads.
        self._payload: dict = deepcopy(payload)

    def read_main_protection(self) -> dict:
        return deepcopy(self._payload)

    def set_payload(self, payload: dict) -> None:
        """Test helper — replace the stored payload."""
        self._payload = deepcopy(payload)
