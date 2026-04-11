"""Tests for StatementFetcher Phase 2 — OAuth2, retry, fallback."""
from __future__ import annotations

import csv
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

from services.recon.statement_fetcher import StatementFetcher, StatementBalance


RECON_DATE = date(2026, 4, 10)


# ── Test: fetch_with_oauth returns StatementBalance list on success ─────────


def test_fetch_with_oauth_success(tmp_path, monkeypatch):
    """fetch_with_oauth returns StatementBalance list when ASPSP responds 200."""
    monkeypatch.setenv("ASPSP_BASE_URL", "https://aspsp.test")
    monkeypatch.setenv("ASPSP_CLIENT_ID", "test-client")
    monkeypatch.setenv("ASPSP_CLIENT_SECRET", "test-secret")

    mock_response_data = {
        "accounts": [
            {
                "account_id": "019d6332-f274-709a-b3a7-983bc8745886",
                "currency": "GBP",
                "closing_balance": "5000.00",
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response_data
    mock_resp.raise_for_status = MagicMock()

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_resp
        mock_client_cls.return_value = mock_client

        fetcher = StatementFetcher(statement_dir=str(tmp_path))
        result = fetcher.fetch_with_oauth(RECON_DATE, access_token="test-token")

    assert len(result) == 1
    assert isinstance(result[0], StatementBalance)
    assert result[0].account_id == "019d6332-f274-709a-b3a7-983bc8745886"
    assert result[0].currency == "GBP"
    assert result[0].balance == Decimal("5000.00")
    assert result[0].statement_date == RECON_DATE
    # Amount MUST be Decimal, never float
    assert isinstance(result[0].balance, Decimal)


# ── Test: retry logic fires 3 times on HTTP 503 ────────────────────────────


def test_fetch_with_oauth_retry_3_times_on_503(tmp_path, monkeypatch):
    """fetch_with_oauth retries 3 times on HTTP 503 with exponential backoff."""
    monkeypatch.setenv("ASPSP_BASE_URL", "https://aspsp.test")

    attempt_count = 0

    def make_503_response():
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 503
        return mock_resp

    def raising_get(*args, **kwargs):
        nonlocal attempt_count
        attempt_count += 1
        raise httpx.HTTPStatusError(
            "Service Unavailable",
            request=MagicMock(),
            response=make_503_response(),
        )

    with patch("httpx.Client") as mock_client_cls, \
         patch("time.sleep") as mock_sleep:
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = raising_get
        mock_client_cls.return_value = mock_client

        fetcher = StatementFetcher(statement_dir=str(tmp_path))
        result = fetcher.fetch_with_oauth(RECON_DATE, access_token="token")

    # Should have tried 3 times (exponential backoff: 1s, 2s, then 3rd attempt no sleep)
    assert attempt_count == 3
    # Backoff sleeps: after attempt 1 (1s), after attempt 2 (2s), no sleep after 3rd
    assert mock_sleep.call_count == 2
    sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
    assert sleep_calls == [1, 2]
    # Returns empty list on exhaustion
    assert result == []


# ── Test: fallback to CSV when ASPSP unreachable ───────────────────────────


def test_fetch_falls_back_to_csv_when_aspsp_missing(tmp_path, monkeypatch):
    """fetch() falls back to CSV when ASPSP_BASE_URL is not set."""
    # Ensure ASPSP_BASE_URL not set
    monkeypatch.delenv("ASPSP_BASE_URL", raising=False)

    # Create a CSV file
    date_str = RECON_DATE.strftime("%Y%m%d")
    csv_path = tmp_path / f"stmt_{date_str}.csv"
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["account_id", "currency", "balance", "statement_date", "source_file"]
        )
        writer.writeheader()
        writer.writerow(
            {
                "account_id": "acc-001",
                "currency": "GBP",
                "balance": "12345.67",
                "statement_date": "2026-04-10",
                "source_file": f"stmt_{date_str}.csv",
            }
        )

    fetcher = StatementFetcher(statement_dir=str(tmp_path))
    result = fetcher.fetch(RECON_DATE)

    assert len(result) == 1
    assert result[0].account_id == "acc-001"
    assert result[0].balance == Decimal("12345.67")
    assert isinstance(result[0].balance, Decimal)


def test_fetch_with_oauth_returns_empty_when_aspsp_url_not_set(tmp_path, monkeypatch):
    """fetch_with_oauth returns [] immediately when ASPSP_BASE_URL not configured."""
    monkeypatch.delenv("ASPSP_BASE_URL", raising=False)
    fetcher = StatementFetcher(statement_dir=str(tmp_path))
    result = fetcher.fetch_with_oauth(RECON_DATE, access_token="any-token")
    assert result == []
