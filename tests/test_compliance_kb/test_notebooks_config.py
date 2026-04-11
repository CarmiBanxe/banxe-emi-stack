"""
tests/test_compliance_kb/test_notebooks_config.py — Notebooks config validation
IL-CKS-01 | banxe-emi-stack

Tests: 3 scenarios validating the compliance_notebooks.yaml is well-formed.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

CONFIG_PATH = Path("config/compliance_notebooks.yaml")

REQUIRED_NOTEBOOKS = [
    "emi-eu-aml",
    "emi-uk-fca",
    "emi-internal-sop",
    "emi-case-history",
]

VALID_SOURCE_TYPES = {"regulation", "guidance", "sop", "sar_template", "policy", "case_study"}

VALID_JURISDICTIONS = {"eu", "uk", "fatf", "eba", "esma"}


@pytest.fixture(scope="module")
def notebooks_config():
    """Load the compliance_notebooks.yaml config."""
    assert CONFIG_PATH.exists(), f"Config file not found: {CONFIG_PATH}"
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestNotebooksConfig:
    def test_all_required_notebooks_present(self, notebooks_config):
        """All 4 required compliance notebooks are defined."""
        notebook_ids = list(notebooks_config.get("notebooks", {}).keys())
        for nb_id in REQUIRED_NOTEBOOKS:
            assert nb_id in notebook_ids, f"Missing notebook: {nb_id}"

    def test_each_notebook_has_required_fields(self, notebooks_config):
        """Each notebook has name, description, tags, jurisdiction, sources."""
        for nb_id, nb_data in notebooks_config["notebooks"].items():
            assert "name" in nb_data, f"{nb_id}: missing 'name'"
            assert "description" in nb_data, f"{nb_id}: missing 'description'"
            assert "tags" in nb_data, f"{nb_id}: missing 'tags'"
            assert isinstance(nb_data["tags"], list), f"{nb_id}: 'tags' must be a list"
            assert "jurisdiction" in nb_data, f"{nb_id}: missing 'jurisdiction'"
            assert nb_data["jurisdiction"] in VALID_JURISDICTIONS, (
                f"{nb_id}: invalid jurisdiction '{nb_data['jurisdiction']}'"
            )
            assert "sources" in nb_data, f"{nb_id}: missing 'sources'"
            assert len(nb_data["sources"]) > 0, f"{nb_id}: must have at least 1 source"

    def test_each_source_has_valid_type(self, notebooks_config):
        """Every source entry has a valid source type."""
        for nb_id, nb_data in notebooks_config["notebooks"].items():
            for src in nb_data.get("sources", []):
                assert "id" in src, f"{nb_id}: source missing 'id'"
                assert "name" in src, f"{nb_id}: source missing 'name'"
                src_type = src.get("type", "")
                assert src_type in VALID_SOURCE_TYPES, (
                    f"{nb_id}/{src.get('id', '?')}: invalid type '{src_type}'"
                )
