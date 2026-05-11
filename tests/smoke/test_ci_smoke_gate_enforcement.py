"""ADR-035 Step 3: CI smoke gate enforcement readiness.

Verifies that the artifacts required for branch-protection enforcement
of the mock smoke gate are present and correctly configured.

Dependency: Step 2 (PR #101) must be merged for the workflow file to exist.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "smoke-gate-mock.yml"
_PROTECTION_JSON_PATH = _REPO_ROOT / ".github" / "protection-update.json"
_EXPECTED_JOB_NAME = "Smoke Gate (mock tier)"


def test_protection_update_json_valid() -> None:
    """protection-update.json exists, parses, and includes the expected check."""
    assert _PROTECTION_JSON_PATH.exists(), f"missing: {_PROTECTION_JSON_PATH}"

    data = json.loads(_PROTECTION_JSON_PATH.read_text())
    checks = data.get("required_status_checks", {}).get("checks", [])
    contexts = [c["context"] for c in checks]

    assert _EXPECTED_JOB_NAME in contexts, (
        f"'{_EXPECTED_JOB_NAME}' not in required checks: {contexts}"
    )


def test_workflow_file_exists_and_job_name_matches() -> None:
    """smoke-gate-mock.yml exists and declares the expected job name.

    This test will fail with a clear message if Step 2 (PR #101) has not
    been merged yet — that is the expected behavior, not a bug.
    """
    if not _WORKFLOW_PATH.exists():
        pytest.fail(
            f"STEP 2 DEPENDENCY: {_WORKFLOW_PATH.name} not found. "
            "PR #101 (ADR-035 Step 2) must be merged before Step 3 "
            "branch-protection can be enforced."
        )

    import yaml  # noqa: PLC0415 — lazy import, yaml may not be installed

    content = yaml.safe_load(_WORKFLOW_PATH.read_text())
    jobs = content.get("jobs", {})
    job_names = [j.get("name", "") for j in jobs.values()]

    assert _EXPECTED_JOB_NAME in job_names, (
        f"Expected job name '{_EXPECTED_JOB_NAME}' not found in workflow jobs: {job_names}"
    )


def test_protection_json_preserves_guardian_checks() -> None:
    """protection-update.json keeps existing guardian required checks."""
    data = json.loads(_PROTECTION_JSON_PATH.read_text())
    checks = data.get("required_status_checks", {}).get("checks", [])
    contexts = [c["context"] for c in checks]

    assert "guardian-factory" in contexts, "guardian-factory check missing"
    assert "guardian-project" in contexts, "guardian-project check missing"
