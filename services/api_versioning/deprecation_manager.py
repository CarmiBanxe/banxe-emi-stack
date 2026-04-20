"""
services/api_versioning/deprecation_manager.py — FCA deprecation notice management
IL-AVD-01 | Phase 44 | banxe-emi-stack
FCA COND 2.2 (transparency). 90-day notice period.
I-27: sunset broadcast is irreversible → HITLProposal.
"""

from __future__ import annotations

from datetime import UTC, datetime
import uuid

from services.api_versioning.models import (
    ApiVersion,
    DeprecationNotice,
    HITLProposal,
)


class DeprecationManager:
    """Manages API deprecation notices and FCA notification workflow."""

    def __init__(self) -> None:
        self._notices: dict[str, DeprecationNotice] = {}

    def mark_deprecated(
        self,
        version: str,
        endpoint: str,
        sunset_date: str,
        migration_endpoint: str,
        actor: str,
    ) -> DeprecationNotice:
        """Mark an endpoint as deprecated with sunset date. FCA COND 2.2."""
        notice_id = f"dep_{uuid.uuid4().hex[:8]}"
        try:
            v = ApiVersion(version.lower())
        except ValueError as exc:
            raise ValueError(f"Unknown version: {version!r}") from exc
        notice = DeprecationNotice(
            notice_id=notice_id,
            version=v,
            endpoint=endpoint,
            sunset_date=sunset_date,
            migration_endpoint=migration_endpoint,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._notices[notice_id] = notice
        return notice

    def check_approaching_sunset(self, days_threshold: int = 30) -> list[DeprecationNotice]:
        """Get notices with sunset within threshold days."""
        today = datetime.now(UTC).date()
        result: list[DeprecationNotice] = []
        for notice in self._notices.values():
            try:
                sunset = datetime.fromisoformat(notice.sunset_date).date()
                delta = (sunset - today).days
                if 0 <= delta <= days_threshold:
                    result.append(notice)
            except ValueError:
                continue
        return result

    def get_all_deprecations(self) -> list[DeprecationNotice]:
        """Get all deprecation notices."""
        return list(self._notices.values())

    def generate_fca_notice(self, version: str, endpoint: str) -> dict:
        """Generate FCA COND 2.2 format deprecation notice."""
        notice = self._find_notice(version, endpoint)
        if notice is None:
            raise ValueError(f"No deprecation notice for {version}/{endpoint}")
        days_left = self.calculate_days_until_sunset(notice.notice_id)
        return {
            "regulatory_ref": "FCA COND 2.2",
            "notice_id": notice.notice_id,
            "version": notice.version.value,
            "endpoint": notice.endpoint,
            "sunset_date": notice.sunset_date,
            "days_until_sunset": days_left,
            "migration_endpoint": notice.migration_endpoint,
            "notice_period_days": 90,
            "created_at": notice.created_at,
            "psd2_ref": "PSD2 Art.30",
            "rfc": "RFC 8594",
        }

    def calculate_days_until_sunset(self, notice_id: str) -> int | None:
        """Calculate days remaining until sunset date."""
        notice = self._notices.get(notice_id)
        if notice is None:
            return None
        try:
            sunset = datetime.fromisoformat(notice.sunset_date).date()
            today = datetime.now(UTC).date()
            return (sunset - today).days
        except ValueError:
            return None

    def trigger_sunset_notification(self, notice_id: str) -> HITLProposal:
        """I-27: broadcast sunset notification is irreversible → HITL."""
        notice = self._notices.get(notice_id)
        if notice is None:
            raise ValueError(f"Notice {notice_id!r} not found")
        return HITLProposal(
            action="trigger_sunset_notification",
            version=notice.version.value,
            requires_approval_from="API_GOVERNANCE",
            reason=f"Broadcast sunset for {notice.endpoint} on {notice.sunset_date}",
        )

    def list_by_version(self, version: str) -> list[DeprecationNotice]:
        """List all deprecation notices for a specific version."""
        return [n for n in self._notices.values() if n.version.value == version]

    def _find_notice(self, version: str, endpoint: str) -> DeprecationNotice | None:
        for notice in self._notices.values():
            if notice.version.value == version and notice.endpoint == endpoint:
                return notice
        return None
