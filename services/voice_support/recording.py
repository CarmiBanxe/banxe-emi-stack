"""
services/voice_support/recording.py — Call recording consent + retention policy
GAP-069 | IMPL-3 | banxe-emi-stack

Consent-to-record is MANDATORY: without an explicit consent flag at call start,
NO recording is authorised and NO audio is stored (UK GDPR + FCA SYSC/DISP).
Retention TTL bounds how long a recording may be kept.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from services.voice_support.models import RecordingDecision

# FCA SYSC 9 / DISP record-keeping — default 6-year retention for support calls.
DEFAULT_RETENTION_DAYS = 2190


class RecordingPolicy:
    """Authorises (or refuses) call recording based on explicit consent."""

    def __init__(self, retention_days: int = DEFAULT_RETENTION_DAYS) -> None:
        self._retention_days = retention_days

    def authorize(self, *, consent_to_record: bool, now: datetime) -> RecordingDecision:
        if not consent_to_record:
            return RecordingDecision(
                allowed=False,
                retention_until=None,
                reason="no consent — recording refused, no audio stored",
            )
        return RecordingDecision(
            allowed=True,
            retention_until=now + timedelta(days=self._retention_days),
            reason="consent given",
        )
