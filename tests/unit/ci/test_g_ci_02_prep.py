"""Unit tests for the S16.5 G-CI-02 prep package.

Validates the protection-update-v2.json manifest's schema invariants and
cross-references each required context against the workflows that actually
declare it. No network calls; no GitHub API access.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PROTECTION_JSON = REPO_ROOT / ".github" / "protection-update-v2.json"
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# Externally-provided checks (GitHub App, not in workflow YAML).
KNOWN_EXTERNAL: set[str] = {"guardian-factory", "guardian-project"}

EXPECTED_TOP_LEVEL_KEYS: set[str] = {
    "_comment_anchors",
    "required_status_checks",
    "enforce_admins",
    "required_pull_request_reviews",
    "restrictions",
}


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(PROTECTION_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def workflow_contents() -> str:
    chunks: list[str] = []
    for yml in sorted(WORKFLOWS_DIR.glob("*.yml")):
        chunks.append(yml.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_protection_update_v2_json_is_valid_json() -> None:
    json.loads(PROTECTION_JSON.read_text(encoding="utf-8"))


def test_protection_update_v2_strict_true(manifest: dict) -> None:
    assert manifest["required_status_checks"]["strict"] is True


def test_protection_update_v2_enforce_admins_false(manifest: dict) -> None:
    assert manifest["enforce_admins"] is False


def test_protection_update_v2_pull_request_reviews_preserved_null(
    manifest: dict,
) -> None:
    """ADR-035 Step 3 baseline left this null; preserve to avoid widening
    the attack surface."""
    assert manifest["required_pull_request_reviews"] is None
    assert manifest["restrictions"] is None


def test_protection_update_v2_required_checks_minimum_count(manifest: dict) -> None:
    checks = manifest["required_status_checks"]["checks"]
    assert len(checks) >= 8, f"expected >= 8 required checks, got {len(checks)}"


def test_protection_update_v2_no_unexpected_keys(manifest: dict) -> None:
    """Schema guard — every top-level key is one of the expected protection
    fields (or the documented `_comment_anchors`)."""
    unexpected = set(manifest.keys()) - EXPECTED_TOP_LEVEL_KEYS
    assert unexpected == set(), f"unexpected top-level keys: {unexpected}"


def test_protection_update_v2_required_checks_all_exist_in_workflows(
    manifest: dict, workflow_contents: str
) -> None:
    """Every check context must either appear as a `name: <ctx>` line in
    some workflow YAML or be on the known-external allowlist."""
    missing: list[str] = []
    for check in manifest["required_status_checks"]["checks"]:
        ctx = check["context"]
        if ctx in KNOWN_EXTERNAL:
            continue
        marker = f"name: {ctx}"
        if marker not in workflow_contents:
            missing.append(ctx)
    assert missing == [], f"contexts not found in any workflow YAML: {missing}"


def test_protection_update_v2_baseline_preserved(manifest: dict) -> None:
    """ADR-035 Step 3 baseline contexts must remain — removing any would
    weaken protection."""
    listed = {c["context"] for c in manifest["required_status_checks"]["checks"]}
    for baseline in (
        "guardian-factory",
        "guardian-project",
        "Smoke Gate (mock tier)",
    ):
        assert baseline in listed, f"baseline context dropped: {baseline}"


def test_protection_update_v2_g_ci_02_new_gates_present(manifest: dict) -> None:
    """S16.5 G-CI-02 newly-required gates."""
    listed = {c["context"] for c in manifest["required_status_checks"]["checks"]}
    for new_gate in (
        "Smoke Gate (real stack)",
        "Pytest (coverage >= 80%)",
        "Ruff lint + format",
        "Semgrep (banxe-rules)",
        "Gitleaks - Secrets Scan",
        "Biome lint + format (Frontend)",
        "Vitest (frontend)",
        "Alembic — schema drift check",
    ):
        assert new_gate in listed, f"G-CI-02 gate missing: {new_gate}"


def test_protection_update_v2_check_entries_well_shaped(manifest: dict) -> None:
    """Every check entry is an object with a single `context` key."""
    for entry in manifest["required_status_checks"]["checks"]:
        assert isinstance(entry, dict), f"non-object check entry: {entry!r}"
        assert "context" in entry, f"missing 'context' in check entry: {entry!r}"
        assert isinstance(entry["context"], str), f"non-string context: {entry!r}"
        assert entry["context"], "empty context string"


def test_protection_update_v2_check_contexts_unique(manifest: dict) -> None:
    """Duplicate contexts in the PUT body are silently deduplicated by
    GitHub but indicate a manifest bug."""
    contexts = [c["context"] for c in manifest["required_status_checks"]["checks"]]
    assert len(contexts) == len(set(contexts)), (
        f"duplicate contexts: {sorted(c for c in contexts if contexts.count(c) > 1)}"
    )
