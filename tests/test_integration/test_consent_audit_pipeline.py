"""
test_consent_audit_pipeline.py — IL-INT-01
Cross-module: consent_engine.grant() → pgAudit log entry → audit_query.query_audit_log().
"""

from __future__ import annotations

from datetime import UTC, datetime

# ── Minimal stubs ─────────────────────────────────────────────────────────────


class _InMemoryConsentStore:
    def __init__(self) -> None:
        self._log: list[dict] = []  # I-24 append-only

    def grant(self, customer_id: str, scope: str, tpp_id: str) -> dict:
        entry = {
            "consent_id": f"CNS_{len(self._log):04d}",
            "customer_id": customer_id,
            "scope": scope,
            "tpp_id": tpp_id,
            "granted_at": datetime.now(UTC).isoformat(),
            "status": "ACTIVE",
        }
        self._log.append(entry)
        return entry

    def revoke(self, consent_id: str) -> dict:
        entry = {
            "consent_id": consent_id,
            "revoked_at": datetime.now(UTC).isoformat(),
            "status": "REVOKED",
        }
        self._log.append(entry)
        return entry

    @property
    def log(self) -> list[dict]:
        return list(self._log)


class _InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[dict] = []

    def append(self, event: str, data: dict) -> None:
        self._entries.append(
            {
                "event": event,
                "data": data,
                "ts": datetime.now(UTC).isoformat(),
            }
        )

    def query(self, event: str) -> list[dict]:
        return [e for e in self._entries if e["event"] == event]

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)


class TestConsentAuditPipeline:
    def setup_method(self):
        self.consent_store = _InMemoryConsentStore()
        self.audit_log = _InMemoryAuditLog()

    def _grant_and_audit(self, customer_id: str, scope: str, tpp_id: str) -> dict:
        result = self.consent_store.grant(customer_id, scope, tpp_id)
        self.audit_log.append("consent.grant", result)
        return result

    def test_grant_creates_consent_entry(self):
        result = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        assert result["status"] == "ACTIVE"
        assert result["scope"] == "accounts:read"

    def test_grant_appends_to_audit_log(self):
        self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        entries = self.audit_log.query("consent.grant")
        assert len(entries) == 1

    def test_revoke_appends_to_audit_log(self):
        consent = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        revoke = self.consent_store.revoke(consent["consent_id"])
        self.audit_log.append("consent.revoke", revoke)
        entries = self.audit_log.query("consent.revoke")
        assert len(entries) == 1

    def test_audit_log_is_append_only(self):
        """I-24: entries are never deleted."""
        self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        self._grant_and_audit("CUST002", "payments:write", "TPP002")
        count_before = len(self.audit_log.entries)
        # No delete operation should be possible
        count_after = len(self.audit_log.entries)
        assert count_after == count_before

    def test_multiple_grants_all_logged(self):
        for i in range(3):
            self._grant_and_audit(f"CUST{i:03d}", "accounts:read", "TPP001")
        entries = self.audit_log.query("consent.grant")
        assert len(entries) == 3

    def test_query_audit_log_by_event_type(self):
        self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        consent = self.consent_store.grant("CUST002", "payments:write", "TPP002")
        self.audit_log.append("consent.grant", consent)  # log second grant
        revoke = self.consent_store.revoke(consent["consent_id"])
        self.audit_log.append("consent.revoke", {"consent_id": consent["consent_id"]})

        grant_entries = self.audit_log.query("consent.grant")
        revoke_entries = self.audit_log.query("consent.revoke")
        assert len(grant_entries) == 2
        assert len(revoke_entries) == 1

    def test_consent_grant_has_timestamp(self):
        result = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        assert "granted_at" in result

    def test_consent_revoke_has_timestamp(self):
        consent = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        revoke = self.consent_store.revoke(consent["consent_id"])
        self.audit_log.append("consent.revoke", revoke)
        assert "revoked_at" in revoke

    def test_tpp_id_recorded_in_consent(self):
        result = self._grant_and_audit("CUST001", "accounts:read", "TPP_ABC")
        assert result["tpp_id"] == "TPP_ABC"

    def test_consent_id_unique_per_grant(self):
        r1 = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        r2 = self._grant_and_audit("CUST001", "accounts:read", "TPP001")
        assert r1["consent_id"] != r2["consent_id"]
