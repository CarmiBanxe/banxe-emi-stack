"""Tests for async polling loop."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.recon.statement_poller import async_poll_with_schedule, health_check


RECON_DATE = date(2026, 4, 10)


# ── Test: async_poll_with_schedule returns paths from first successful poll ──


@pytest.mark.asyncio
async def test_async_poll_returns_paths_from_first_window(tmp_path):
    """async_poll_with_schedule returns file paths when first poll window succeeds."""
    expected_paths = [tmp_path / "camt053_20260410_1234.xml"]
    for p in expected_paths:
        p.write_text("<Document/>")

    # Mock datetime.now to return a time past the 06:00 window
    # so no sleep is needed, and poll_statements returns paths immediately
    with patch("services.recon.statement_poller.datetime") as mock_dt, \
         patch("services.recon.statement_poller.poll_statements") as mock_poll:

        from datetime import datetime, timezone
        # Return a time that is already past all windows (13:00 UTC)
        mock_dt.now.return_value = datetime(2026, 4, 10, 13, 0, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        mock_poll.return_value = expected_paths

        result = await async_poll_with_schedule(RECON_DATE)

    assert result == expected_paths


@pytest.mark.asyncio
async def test_async_poll_returns_empty_when_all_windows_miss():
    """async_poll_with_schedule returns [] when no data across all windows."""
    with patch("services.recon.statement_poller.datetime") as mock_dt, \
         patch("services.recon.statement_poller.poll_statements") as mock_poll, \
         patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:

        from datetime import datetime, timezone
        # Past all windows — no sleep needed
        mock_dt.now.return_value = datetime(2026, 4, 10, 13, 0, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)
        # All polls return empty
        mock_poll.return_value = []

        result = await async_poll_with_schedule(RECON_DATE)

    assert result == []


@pytest.mark.asyncio
async def test_async_poll_stops_after_first_success():
    """async_poll_with_schedule stops trying after first non-empty result."""
    call_count = 0

    def mock_poll(recon_date):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [Path("/tmp/test.xml")]
        return []

    with patch("services.recon.statement_poller.datetime") as mock_dt, \
         patch("services.recon.statement_poller.poll_statements", side_effect=mock_poll):

        from datetime import datetime, timezone
        mock_dt.now.return_value = datetime(2026, 4, 10, 13, 0, 0, tzinfo=timezone.utc)
        mock_dt.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

        result = await async_poll_with_schedule(RECON_DATE)

    # Should stop after first success — only 1 call
    assert call_count == 1
    assert result == [Path("/tmp/test.xml")]


# ── Test: health_check returns False when adorsys unreachable ───────────────


def test_health_check_returns_false_when_unreachable():
    """health_check returns False when adorsys gateway is not reachable."""
    import httpx

    with patch("httpx.get") as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = health_check()

    assert result is False


def test_health_check_returns_false_on_non_200():
    """health_check returns False when adorsys returns non-200 status."""
    with patch("httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_get.return_value = mock_resp
        result = health_check()

    assert result is False


def test_health_check_returns_true_on_200():
    """health_check returns True when adorsys gateway responds with 200."""
    with patch("httpx.get") as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp
        result = health_check()

    assert result is True
