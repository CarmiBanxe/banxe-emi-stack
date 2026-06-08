"""
tests/test_intent_layer/test_catalog.py — IntentCatalog: load, resolve, validate
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack
"""

from __future__ import annotations

import pytest

from services.intent_layer.catalog import IntentCatalog, UnresolvableProcessError
from services.intent_layer.models import ProcessRef

from .conftest import INTENT_MAP, NINE_CAPABILITIES, REGISTRY


def test_every_process_id_resolves_to_a_versioned_ref(catalog):
    for intent, _capability, process_id in NINE_CAPABILITIES:
        definition = catalog.lookup(intent)
        assert definition is not None
        assert definition.process_refs == (ProcessRef(process_id, "1.0.0"),)


def test_exact_and_alias_keys_index_to_same_definition(catalog):
    by_intent = catalog.lookup("pay")
    by_alias = catalog.lookup("send money")
    assert by_intent is by_alias
    assert by_intent.capability == "Payments"


def test_lookup_is_case_and_whitespace_insensitive(catalog):
    assert catalog.lookup("  SEND   MONEY ") is catalog.lookup("send money")


def test_lookup_unknown_text_returns_none(catalog):
    assert catalog.lookup("teleport me to mars") is None


def test_by_intent_resolves_canonical_token_only(catalog):
    assert catalog.by_intent("pay") is not None
    # an alias is not a canonical intent token
    assert catalog.by_intent("send money") is None
    assert catalog.by_intent("nope") is None


def test_definitions_exposes_all_rows(catalog):
    assert len(catalog.definitions) == len(INTENT_MAP["intents"])


def test_missing_registry_entry_raises_at_load():
    bad_map = {
        "intents": [
            {
                "intent": "ghost",
                "aliases": [],
                "capability": "X",
                "process_ids": ["no-such-process"],
            }
        ]
    }
    with pytest.raises(UnresolvableProcessError, match="no-such-process"):
        IntentCatalog.from_data(bad_map, REGISTRY)


def test_from_files_round_trips(map_files):
    map_path, reg_path = map_files
    catalog = IntentCatalog.from_files(map_path, reg_path)
    assert catalog.lookup("exchange").process_refs == (ProcessRef("fx-exchange", "1.0.0"),)


def test_process_ref_rejects_empty_fields():
    with pytest.raises(ValueError, match="process_id"):
        ProcessRef("", "1.0.0")
    with pytest.raises(ValueError, match="version"):
        ProcessRef("x", "")


def test_process_ref_as_dict_matches_schema_shape():
    assert ProcessRef("fx-exchange", "1.0.0").as_dict() == {
        "process_id": "fx-exchange",
        "version": "1.0.0",
    }
