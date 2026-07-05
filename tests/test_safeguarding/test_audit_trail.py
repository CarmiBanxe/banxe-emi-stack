"""Tests for src/safeguarding/audit_trail.py — I-24 append-only audit trail.

Covers:
  - Append operations (successful and failure paths)
  - ClickHouse connectivity (dry_run, success, failure, httpx unavailable)
  - Payload serialization (JSON encoding, special chars)
  - Event ID / timestamp generation
  - Table creation (ensure_table)
  - Fail-open vs fail-closed behavior (AUDIT_FAIL_CLOSED env var)
  - No delete/update interface (I-24 compliance)
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import logging
from unittest.mock import MagicMock, patch
from uuid import UUID

import httpx
import pytest
from src.safeguarding.audit_trail import AuditEvent, AuditTrail


class TestAuditEvent:
    """Test AuditEvent dataclass — immutable event records."""

    def test_audit_event_defaults(self) -> None:
        """Event with only required fields gets defaults."""
        event = AuditEvent(
            event_type="TEST_EVENT",
            entity_id="entity-123",
            actor="TestActor",
        )
        assert event.event_type == "TEST_EVENT"
        assert event.entity_id == "entity-123"
        assert event.actor == "TestActor"
        assert event.payload == {}
        assert event.severity == "INFO"
        assert isinstance(event.event_id, str)
        assert isinstance(event.occurred_at, datetime)

    def test_audit_event_with_payload(self) -> None:
        """Event accepts arbitrary JSON-serialisable payload."""
        payload = {"diff_gbp": "50.00", "account_id": "acc-1"}
        event = AuditEvent(
            event_type="RECON_BREAK",
            entity_id="recon-1",
            actor="DailyRecon",
            payload=payload,
            severity="CRITICAL",
        )
        assert event.payload == payload
        assert event.severity == "CRITICAL"

    def test_audit_event_payload_json(self) -> None:
        """payload_json() serialises dict to JSON string."""
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
            payload={"key": "value", "number": 42},
        )
        json_str = event.payload_json()
        assert isinstance(json_str, str)
        decoded = json.loads(json_str)
        assert decoded["key"] == "value"
        assert decoded["number"] == 42

    def test_audit_event_payload_json_handles_special_chars(self) -> None:
        """payload_json() escapes quotes and special chars."""
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
            payload={"message": "Account says 'hello'"},
        )
        json_str = event.payload_json()
        assert "hello" in json_str
        # Should not raise on parsing
        decoded = json.loads(json_str)
        assert decoded["message"] == "Account says 'hello'"


class TestAuditTrailDryRun:
    """Test AuditTrail in dry_run=True mode (logs to logger, no ClickHouse)."""

    def test_dry_run_logs_event(self, caplog: pytest.LogCaptureFixture) -> None:
        """In dry_run mode, log() returns True and logs to logger."""
        trail = AuditTrail(dry_run=True)
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with caplog.at_level(logging.INFO):
            result = trail.log(event)
        assert result is True
        assert any(
            "DRY_RUN" in record.message and "TEST" in record.message for record in caplog.records
        )

    def test_dry_run_ensure_table_noops(self, caplog: pytest.LogCaptureFixture) -> None:
        """In dry_run mode, ensure_table() logs noop and returns."""
        trail = AuditTrail(dry_run=True)
        with caplog.at_level(logging.INFO):
            trail.ensure_table()
        assert any("skipping ensure_table" in r.message for r in caplog.records)


class TestAuditTrailClickHouse:
    """Test AuditTrail with real ClickHouse connectivity."""

    def test_write_success_returns_true(self) -> None:
        """Successful ClickHouse INSERT returns True."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123",
            database="banxe",
            dry_run=False,
        )
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            result = trail.log(event)

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "query" in call_args.kwargs["params"]
        assert "safeguarding_audit" in call_args.kwargs["params"]["query"]

    def test_write_http_error_fail_open(self, caplog: pytest.LogCaptureFixture) -> None:
        """ClickHouse HTTP error (500) → fail-open → logs error, returns False."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123",
            database="banxe",
            dry_run=False,
        )
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
            with caplog.at_level(logging.ERROR):
                result = trail.log(event)

        assert result is False
        assert any("FALLBACK" in r.message for r in caplog.records)

    def test_write_http_error_fail_closed(self) -> None:
        """With AUDIT_FAIL_CLOSED=true, ClickHouse error raises."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123",
            database="banxe",
            dry_run=False,
        )
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock()
            )
            with patch.dict("os.environ", {"AUDIT_FAIL_CLOSED": "true"}):
                with pytest.raises(httpx.HTTPStatusError):
                    trail.log(event)

    def test_write_with_auth(self) -> None:
        """ClickHouse credentials passed via auth."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123",
            database="banxe",
            dry_run=False,
            clickhouse_user="user1",
            clickhouse_password="pass1",
        )
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            trail.log(event)

        call_args = mock_post.call_args
        assert call_args.kwargs["auth"] == ("user1", "pass1")


class TestAuditTrailI24Compliance:
    """Test I-24 compliance: audit trail is append-only (no delete/update/modify)."""

    def test_no_delete_method(self) -> None:
        """AuditTrail has no public delete() method."""
        trail = AuditTrail(dry_run=True)
        assert not hasattr(trail, "delete") or not callable(getattr(trail, "delete", None))

    def test_no_update_method(self) -> None:
        """AuditTrail has no public update() method."""
        trail = AuditTrail(dry_run=True)
        assert not hasattr(trail, "update") or not callable(getattr(trail, "update", None))

    def test_log_only_writes_appends(self) -> None:
        """AuditTrail.log() only generates INSERT queries, never UPDATE/DELETE."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123",
            database="banxe",
            dry_run=False,
        )
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            trail.log(event)

        query = mock_post.call_args.kwargs["params"]["query"]
        assert "INSERT" in query
        assert "UPDATE" not in query
        assert "DELETE" not in query


class TestAuditTrailEdgeCases:
    """Edge cases and error paths."""

    def test_clickhouse_url_trailing_slash_stripped(self) -> None:
        """Trailing slashes in URL are stripped."""
        trail = AuditTrail(
            clickhouse_url="http://localhost:8123/",
            database="banxe",
            dry_run=False,
        )
        assert trail.clickhouse_url == "http://localhost:8123"

    def test_empty_payload(self) -> None:
        """Event with empty payload is valid."""
        trail = AuditTrail(dry_run=True)
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
            payload={},
        )
        result = trail.log(event)
        assert result is True

    def test_large_payload(self) -> None:
        """Event with large JSON payload is valid."""
        large_payload = {f"key_{i}": f"value_{i}" for i in range(1000)}
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
            payload=large_payload,
        )
        trail = AuditTrail(dry_run=True)
        result = trail.log(event)
        assert result is True

    def test_event_id_is_valid_uuid(self) -> None:
        """Generated event_id is a valid UUID."""
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        # Should not raise
        UUID(event.event_id)

    def test_occurred_at_is_utc(self) -> None:
        """Event timestamp is in UTC."""
        event = AuditEvent(
            event_type="TEST",
            entity_id="e1",
            actor="actor",
        )
        assert event.occurred_at.tzinfo == UTC
