from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
import hashlib
import uuid

from services.api_gateway.models import (
    APIKey,
    APIKeyStorePort,
    InMemoryAPIKeyStore,
    KeyStatus,
    UsageTier,
)


class APIKeyManager:
    """Manages API key lifecycle: create, rotate, revoke, verify."""

    def __init__(self, store: APIKeyStorePort | None = None) -> None:
        self._store: APIKeyStorePort = store or InMemoryAPIKeyStore()

    def _hash_key(self, raw_key: str) -> str:
        return hashlib.sha256(raw_key.encode()).hexdigest()  # I-12

    def create_key(
        self,
        name: str,
        owner_id: str,
        scope: list[str],
        tier: UsageTier,
    ) -> tuple[str, APIKey]:
        """
        Generate a new API key.
        Returns (raw_key, APIKey) — raw_key returned ONCE, never stored.
        """
        raw_key = f"bxk_{uuid.uuid4().hex}"
        key_hash = self._hash_key(raw_key)
        api_key = APIKey(
            key_id=str(uuid.uuid4()),
            name=name,
            key_hash=key_hash,
            scope=scope,
            tier=tier,
            status=KeyStatus.ACTIVE,
            created_at=datetime.now(UTC),
            owner_id=owner_id,
        )
        self._store.save(api_key)
        return raw_key, api_key

    def rotate_key(self, key_id: str) -> tuple[str, APIKey]:
        """
        Rotate an API key: mark old key ROTATED, create new key.
        Returns (new_raw_key, new_api_key).
        """
        old_key = self._store.get_by_id(key_id)
        if old_key is None:
            raise ValueError(f"Key not found: {key_id}")

        now = datetime.now(UTC)
        rotated = replace(old_key, status=KeyStatus.ROTATED, rotated_at=now)
        self._store.update(rotated)

        new_raw_key = f"bxk_{uuid.uuid4().hex}"
        new_hash = self._hash_key(new_raw_key)
        new_key = APIKey(
            key_id=str(uuid.uuid4()),
            name=old_key.name,
            key_hash=new_hash,
            scope=old_key.scope,
            tier=old_key.tier,
            status=KeyStatus.ACTIVE,
            created_at=now,
            owner_id=old_key.owner_id,
        )
        self._store.save(new_key)
        return new_raw_key, new_key

    def revoke_key(self, key_id: str, actor: str) -> dict:  # noqa: ARG002
        """
        Flag key for revocation — HITL L4 required (I-27).
        Actual revocation requires Compliance Officer approval.
        """
        return {"status": "HITL_REQUIRED", "key_id": key_id}

    def verify_key(self, raw_key: str) -> APIKey | None:
        """Hash raw_key, look up by hash, return if ACTIVE."""
        key_hash = self._hash_key(raw_key)
        api_key = self._store.get_by_hash(key_hash)
        if api_key is not None and api_key.status == KeyStatus.ACTIVE:
            return api_key
        return None

    def get_key(self, key_id: str) -> APIKey | None:
        return self._store.get_by_id(key_id)

    def list_keys(self, owner_id: str) -> list[APIKey]:
        return self._store.list_by_owner(owner_id)
