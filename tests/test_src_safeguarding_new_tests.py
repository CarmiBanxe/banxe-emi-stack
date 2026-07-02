"""Additional tests for audit_trail coverage — I-24 hardening."""

from __future__ import annotations

from datetime import date
from decimal import Decimal


class TestAuditTrailCoverage:
    def _trail(self, dry_run=True):
        from src.safeguarding.audit_trail import AuditTrail

        return AuditTrail(dry_run=dry_run)

    def _event(self, event_type="RECON_BREAK"):
        from src.safeguarding.audit_trail import AuditEvent

        return AuditEvent(
            event_type=event_type,
            entity_id="recon-2026-04-13",
            actor="DailyReconciliation",
            payload={"diff_gbp": "50.00"},
            severity="CRITICAL",
        )

    def test_log_with_fail_closed_raises_on_exception(self):
        """Test that AUDIT_FAIL_CLOSED=true raises exception (line 136)."""
        import os
        import pytest
        from unittest.mock import patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://bad.local:1")
        with patch.dict(os.environ, {"AUDIT_FAIL_CLOSED": "true"}):
            with patch.object(trail, "_write", side_effect=RuntimeError("Connection failed")):
                with pytest.raises(RuntimeError, match="Connection failed"):
                    trail.log(self._event())

    def test_write_no_httpx_import_logs_critical(self, caplog):
        """Test httpx ImportError fallback in _write() (lines 153-162)."""
        from unittest.mock import patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://localhost:8123")
        with patch.dict("sys.modules", {"httpx": None}):
            result = trail._write(self._event())
            assert result is False
            assert any("httpx not installed" in record.message for record in caplog.records)

    def test_write_success_clickhouse_post(self):
        """Test successful ClickHouse POST (lines 173-180)."""
        from unittest.mock import MagicMock, patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://localhost:8123")
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            result = trail._write(self._event())
            assert result is True
            assert mock_post.called

    def test_ensure_table_creates_ddl(self):
        """Test ensure_table sends CREATE TABLE DDL (lines 198-224)."""
        from unittest.mock import MagicMock, patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://localhost:8123")
        with patch("httpx.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_post.return_value = mock_resp

            trail.ensure_table()
            assert mock_post.called
            call_args = mock_post.call_args
            assert "query" in call_args.kwargs["params"]
            assert "CREATE TABLE" in call_args.kwargs["params"]["query"]

    def test_ensure_table_handles_exception(self, caplog):
        """Test ensure_table exception handling (lines 230-231)."""
        from unittest.mock import patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://localhost:8123")
        with patch("httpx.post", side_effect=Exception("Network error")):
            trail.ensure_table()  # must not raise
            assert any("failed to ensure table" in record.message for record in caplog.records)

    def test_log_fail_open_returns_false_on_exception(self):
        """Test that AUDIT_FAIL_CLOSED=false returns False (line 137)."""
        import os
        from unittest.mock import patch
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=False, clickhouse_url="http://bad.local:1")
        with patch.dict(os.environ, {"AUDIT_FAIL_CLOSED": "false"}):
            with patch.object(trail, "_write", side_effect=RuntimeError("Connection failed")):
                result = trail.log(self._event())
                assert result is False

    def test_write_returns_true_in_dry_run(self):
        """Test that _write returns True in dry_run mode (lines 141-149)."""
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=True, clickhouse_url="http://localhost:8123")
        result = trail._write(self._event())
        assert result is True

    def test_ensure_table_returns_early_in_dry_run(self):
        """Test ensure_table returns without error in dry_run (lines 189-190)."""
        from src.safeguarding.audit_trail import AuditTrail

        trail = AuditTrail(dry_run=True, clickhouse_url="http://localhost:8123")
        trail.ensure_table()  # must return without raising
