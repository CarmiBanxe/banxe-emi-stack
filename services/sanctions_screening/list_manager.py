from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json

from services.sanctions_screening.models import (
    ListSource,
    ListStore,
    SanctionsList,
)


class ListManager:
    def __init__(self, list_store: ListStore) -> None:
        self._store = list_store

    def load_list(
        self,
        source: ListSource,
        entries: list[dict],
        version: str,
    ) -> SanctionsList:
        """I-12: computes SHA-256 checksum of entries."""
        checksum = self._checksum(entries)
        ts = datetime.now(UTC).isoformat()
        lst_id = f"lst_{source.value}_{version}"
        lst = SanctionsList(
            list_id=lst_id,
            source=source,
            version=version,
            entry_count=len(entries),
            last_updated=ts,
            checksum=checksum,
        )
        self._store.save_list(lst)
        return lst

    def update_list(
        self,
        source: ListSource,
        new_entries: list[dict],
        version: str,
    ) -> SanctionsList:
        """Verifies new checksum ≠ current (prevents duplicate updates)."""
        new_checksum = self._checksum(new_entries)
        current = self._store.get_list(source)
        if current is not None and current.checksum == new_checksum:
            raise ValueError(f"List {source} already at this version (checksum match)")
        return self.load_list(source, new_entries, version)

    def get_active_lists(self) -> list[SanctionsList]:
        results = []
        for source in ListSource:
            lst = self._store.get_list(source)
            if lst is not None:
                results.append(lst)
        return results

    def get_list_version(self, source: ListSource) -> str | None:
        lst = self._store.get_list(source)
        return lst.version if lst else None

    def schedule_refresh(self, source: ListSource) -> dict:
        return {"scheduled": True, "source": source.value}

    def compare_versions(
        self,
        source: ListSource,
        old_version: str,
        new_version: str,
    ) -> dict:
        current = self._store.get_list(source)
        return {
            "source": source.value,
            "old_version": old_version,
            "new_version": new_version,
            "current_version": current.version if current else None,
            "changed": old_version != new_version,
        }

    # --- helpers ---

    @staticmethod
    def _checksum(entries: list[dict]) -> str:
        serialised = json.dumps(entries, sort_keys=True).encode()
        return hashlib.sha256(serialised).hexdigest()
