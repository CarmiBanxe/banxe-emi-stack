"""
api/routers/user_preferences.py
IL-UPS-01 | Phase 39 | banxe-emi-stack

User Preferences REST API — 9 endpoints under /v1/preferences/.
GDPR-compliant: consent withdrawal and erasure return HITL proposals (I-27).
NOTE: Specific paths (consents/, notifications/, export) must be registered BEFORE
      generic /{category}/{key} to avoid route shadowing.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.user_preferences.consent_manager import ConsentManager
from services.user_preferences.data_export import DataExport
from services.user_preferences.models import (
    ConsentType,
    NotificationChannel,
    PreferenceCategory,
)
from services.user_preferences.notification_preferences import NotificationPreferences
from services.user_preferences.preference_store import PreferenceStore

router = APIRouter(tags=["user-preferences"])

_pref_store = PreferenceStore()
_consent_mgr = ConsentManager()
_notif_prefs = NotificationPreferences()
_data_export = DataExport()


class SetPreferenceRequest(BaseModel):
    value: str


class GrantConsentRequest(BaseModel):
    consent_type: str
    ip_address: str
    channel: str


class WithdrawConsentRequest(BaseModel):
    consent_type: str


class SetNotificationPrefRequest(BaseModel):
    enabled: bool | None = None
    quiet_hours_start: int | None = None
    quiet_hours_end: int | None = None


class DataExportRequest(BaseModel):
    format: str = "json"


@router.get("/preferences/{user_id}")
def get_all_preferences(user_id: str) -> dict:
    """Return all preferences for user merged with defaults."""
    return {
        "user_id": user_id,
        "preferences": _pref_store.list_preferences(user_id),
    }


# ── Consent endpoints (must be before generic /{category}/{key}) ─────────────


@router.get("/preferences/{user_id}/consents")
def list_consents(user_id: str) -> dict:
    """List all consent records for user."""
    records = _consent_mgr.list_consents(user_id)
    return {
        "user_id": user_id,
        "consents": [
            {
                "id": r.id,
                "consent_type": r.consent_type.value,
                "status": r.status,
                "granted_at": r.granted_at.isoformat(),
                "withdrawn_at": r.withdrawn_at.isoformat() if r.withdrawn_at else None,
            }
            for r in records
        ],
    }


@router.post("/preferences/{user_id}/consents/grant")
def grant_consent(user_id: str, body: GrantConsentRequest) -> dict:
    """Grant consent for a consent type."""
    try:
        ct = ConsentType(body.consent_type.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown consent type: {body.consent_type}")
    record = _consent_mgr.grant_consent(user_id, ct, body.ip_address, body.channel)
    return {
        "id": record.id,
        "user_id": user_id,
        "consent_type": record.consent_type.value,
        "status": record.status,
        "granted_at": record.granted_at.isoformat(),
    }


@router.post("/preferences/{user_id}/consents/withdraw")
def withdraw_consent(user_id: str, body: WithdrawConsentRequest) -> dict:
    """Withdraw consent — returns HITL proposal (I-27)."""
    try:
        ct = ConsentType(body.consent_type.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown consent type: {body.consent_type}")
    try:
        proposal = _consent_mgr.withdraw_consent(user_id, ct)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "hitl_required": True,
        "action": proposal.action,
        "resource_id": proposal.resource_id,
        "requires_approval_from": proposal.requires_approval_from,
        "reason": proposal.reason,
        "autonomy_level": proposal.autonomy_level,
    }


# ── Notification endpoints (must be before generic /{category}/{key}) ─────────


@router.get("/preferences/{user_id}/notifications")
def list_notification_prefs(user_id: str) -> dict:
    """List all notification channel preferences for user."""
    prefs = _notif_prefs.list_channel_prefs(user_id)
    return {
        "user_id": user_id,
        "channels": [
            {
                "channel": p.channel.value,
                "enabled": p.enabled,
                "frequency_cap_per_day": p.frequency_cap_per_day,
                "quiet_hours_start": p.quiet_hours_start,
                "quiet_hours_end": p.quiet_hours_end,
            }
            for p in prefs
        ],
    }


@router.put("/preferences/{user_id}/notifications/{channel}")
def set_notification_pref(
    user_id: str,
    channel: str,
    body: SetNotificationPrefRequest,
) -> dict:
    """Update notification preferences for a channel."""
    try:
        ch = NotificationChannel(channel.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown channel: {channel}")
    prefs = _notif_prefs.get_channel_prefs(user_id, ch)
    if body.enabled is not None:
        prefs = _notif_prefs.set_channel_enabled(user_id, ch, body.enabled)
    if body.quiet_hours_start is not None and body.quiet_hours_end is not None:
        try:
            prefs = _notif_prefs.set_quiet_hours(
                user_id, ch, body.quiet_hours_start, body.quiet_hours_end
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return {
        "user_id": user_id,
        "channel": prefs.channel.value,
        "enabled": prefs.enabled,
        "frequency_cap_per_day": prefs.frequency_cap_per_day,
        "quiet_hours_start": prefs.quiet_hours_start,
        "quiet_hours_end": prefs.quiet_hours_end,
    }


# ── Export endpoint (must be before generic /{category}/{key}) ────────────────


@router.post("/preferences/{user_id}/export")
def request_data_export(user_id: str, body: DataExportRequest) -> dict:
    """Request a GDPR data export."""
    request = _data_export.request_export(user_id, body.format)
    completed = _data_export.complete_export(request.id, user_id)
    return {
        "request_id": completed.id,
        "user_id": user_id,
        "status": completed.status,
        "format": completed.format,
        "export_hash": completed.export_hash,
        "requested_at": completed.requested_at.isoformat(),
        "completed_at": completed.completed_at.isoformat() if completed.completed_at else None,
    }


# ── Generic preference endpoints (must be LAST — catch-all path params) ───────


@router.put("/preferences/{user_id}/{category}/{key}")
def set_preference(user_id: str, category: str, key: str, body: SetPreferenceRequest) -> dict:
    """Set a specific preference key."""
    try:
        cat = PreferenceCategory(category.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown category: {category}")
    try:
        pref = _pref_store.set_preference(user_id, cat, key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "user_id": user_id,
        "category": pref.category.value,
        "key": pref.key,
        "value": pref.value,
        "updated_at": pref.updated_at.isoformat(),
    }


@router.post("/preferences/{user_id}/{category}/reset")
def reset_category(user_id: str, category: str) -> dict:
    """Reset all preferences in a category to defaults."""
    try:
        cat = PreferenceCategory(category.upper())
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown category: {category}")
    prefs = _pref_store.reset_to_defaults(user_id, cat)
    return {
        "user_id": user_id,
        "category": cat.value,
        "reset_count": len(prefs),
        "preferences": [{"key": p.key, "value": p.value} for p in prefs],
    }
