"""
services/intent_layer/catalog.py — intent→process_ref catalog (S3 inputs)
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

Loads the two S3 artefacts and joins them into a resolved, query-ready catalog:
  - banxe-business-processes/ai-agent-context/intent-process-map.yaml
      (intent + aliases + capability + process_ids)
  - banxe-business-processes/ai-agent-context/processes-registry.json
      ({process_id, version}) — the version source for each process_ref.

Every process_id in the map MUST exist in the registry (mirrors the repo's own
validate_resolvable.py). A bare process_id with no registry entry is a construction
error, surfaced loudly at load time — never silently dispatched.

The catalog is pure data: it can be built from parsed dicts (unit tests / DI) or from
files (composition root). It hard-depends on neither agent repo.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from services.intent_layer.models import IntentDefinition, ProcessRef


def _normalise(text: str) -> str:
    """Canonical lookup key: lowercased, collapsed internal whitespace, trimmed."""
    return " ".join(text.lower().split())


class UnresolvableProcessError(ValueError):
    """Raised when an intent maps to a process_id absent from the registry."""


class IntentCatalog:
    """Resolved intent→process_ref lookup over the S3 map + registry."""

    def __init__(self, definitions: list[IntentDefinition]) -> None:
        self._definitions: list[IntentDefinition] = list(definitions)
        self._index: dict[str, IntentDefinition] = {}
        for d in self._definitions:
            self._index[_normalise(d.intent)] = d
            for alias in d.aliases:
                self._index[_normalise(alias)] = d

    @property
    def definitions(self) -> list[IntentDefinition]:
        """All intent definitions — passed to the LLM port as fuzzy-match candidates."""
        return list(self._definitions)

    def lookup(self, key: str) -> IntentDefinition | None:
        """Exact/alias lookup on the normalised key; None when nothing matches."""
        return self._index.get(_normalise(key))

    def by_intent(self, intent: str) -> IntentDefinition | None:
        """Resolve a canonical intent token (used to re-validate an LLM proposal)."""
        d = self._index.get(_normalise(intent))
        return d if d is not None and _normalise(d.intent) == _normalise(intent) else None

    # ── Construction ────────────────────────────────────────────────────────────

    @classmethod
    def from_data(cls, intent_map: dict[str, Any], registry: dict[str, Any]) -> IntentCatalog:
        """Build from already-parsed YAML/JSON structures (the DI / test entry point)."""
        versions = {
            entry["process_id"]: entry["version"] for entry in registry.get("processes", [])
        }
        definitions: list[IntentDefinition] = []
        for row in intent_map.get("intents", []):
            refs: list[ProcessRef] = []
            for pid in row.get("process_ids", []):
                if pid not in versions:
                    raise UnresolvableProcessError(
                        f"intent {row['intent']!r} → process_id {pid!r} "
                        "not present in processes-registry.json"
                    )
                refs.append(ProcessRef(process_id=pid, version=versions[pid]))
            definitions.append(
                IntentDefinition(
                    intent=row["intent"],
                    aliases=tuple(row.get("aliases", [])),
                    capability=row["capability"],
                    process_refs=tuple(refs),
                )
            )
        return cls(definitions)

    @classmethod
    def from_files(cls, map_path: str | Path, registry_path: str | Path) -> IntentCatalog:
        """Build from the two S3 files on disk (the composition-root entry point)."""
        import yaml  # local import — keeps PyYAML optional for pure-data test paths

        intent_map = yaml.safe_load(Path(map_path).read_text(encoding="utf-8"))
        registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
        return cls.from_data(intent_map, registry)
