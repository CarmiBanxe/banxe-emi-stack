"""
test_gitleaks_audit_script.py — Unit tests for the ADR-032 gitleaks
coverage audit helper (scripts/secret-rotation-gitleaks-audit.py).

Verifies the parsing + matching + exit-code logic against in-memory toml
fixtures. No dependency on the live .gitleaks.toml file or gitleaks itself.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_audit_module() -> ModuleType:
    """Load scripts/secret-rotation-gitleaks-audit.py as a module.

    The script file uses hyphens in its name, so it cannot be imported
    directly via `import scripts.secret-rotation-gitleaks-audit`. We load
    it via importlib spec.
    """
    repo_root = Path(__file__).resolve().parents[3]
    script_path = repo_root / "scripts" / "secret-rotation-gitleaks-audit.py"
    spec = importlib.util.spec_from_file_location("_gitleaks_audit_module", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["_gitleaks_audit_module"] = module
    spec.loader.exec_module(module)
    return module


def _write_toml(tmp_path: Path, body: str) -> Path:
    cfg = tmp_path / ".gitleaks.toml"
    cfg.write_text(body)
    return cfg


def test_audit_reports_covered_for_pattern_matching_matrix_entry(tmp_path: Path) -> None:
    audit_mod = _load_audit_module()
    cfg = _write_toml(
        tmp_path,
        """
title = "test"

[[rules]]
id = "test-marble"
description = "test"
regex = """
        + "'''MARBLE_API_KEY\\s*=\\s*[A-Za-z0-9]{8,}'''"
        + "\n",
    )
    exit_code, report = audit_mod.audit(cfg)
    by_name = dict(report)
    assert by_name["MARBLE_API_KEY"] is True
    # And entries not covered remain False
    assert by_name["FCA_REGDATA_PASSWORD"] is False
    assert exit_code == 1  # at least one missing


def test_audit_reports_missing_for_unmatched_matrix_entry(tmp_path: Path) -> None:
    audit_mod = _load_audit_module()
    # Empty config — no rules
    cfg = _write_toml(tmp_path, 'title = "empty"\n')
    exit_code, report = audit_mod.audit(cfg)
    assert exit_code == 1
    assert all(covered is False for _name, covered in report)


def test_audit_exit_code_zero_when_all_covered(tmp_path: Path) -> None:
    audit_mod = _load_audit_module()
    # Build a config with one broad regex that matches every matrix entry.
    cfg = _write_toml(
        tmp_path,
        """
title = "all-covered"

[[rules]]
id = "catch-all"
description = "matches any uppercase env-var assignment"
regex = """
        + "'''[A-Z_][A-Z0-9_]+\\s*=\\s*[A-Za-z0-9_\\-]{8,}'''"
        + "\n",
    )
    exit_code, report = audit_mod.audit(cfg)
    assert exit_code == 0
    assert all(covered for _name, covered in report)


def test_audit_handles_missing_config_file_gracefully(tmp_path: Path) -> None:
    audit_mod = _load_audit_module()
    missing = tmp_path / "does-not-exist.toml"
    exit_code, report = audit_mod.audit(missing)
    # All entries missing → exit 1, but no crash
    assert exit_code == 1
    assert len(report) == len(audit_mod.ADR_032_MATRIX_SECRET_NAMES)
    assert all(covered is False for _name, covered in report)


def test_audit_matrix_list_includes_all_adr032_canonical_secret_types() -> None:
    """Guard: ensure the matrix list in the audit script matches the
    set of secret types ADR-032 §Cadence-and-ownership matrix declares."""
    audit_mod = _load_audit_module()
    expected_substrings = {
        "KC_CLIENT_SECRET_",
        "KC_BOOT_ADMIN_PASSWORD",
        "KC_DB_PASSWORD",
        "AUTH_SECRET_KEY",
        "POSTGRES_PASSWORD",
        "CLICKHOUSE_PASSWORD",
        "GITHUB_PAT_",
        "MARBLE_API_KEY",
        "JUBE_PASSWORD",
        "SUMSUB_APP_TOKEN",
        "SUMSUB_WEBHOOK_SECRET",
        "TELEGRAM_BOT_TOKEN",
        "FCA_REGDATA_PASSWORD",
    }
    matrix_text = " ".join(audit_mod.ADR_032_MATRIX_SECRET_NAMES)
    for sub in expected_substrings:
        assert sub in matrix_text, f"missing matrix coverage for {sub}"
