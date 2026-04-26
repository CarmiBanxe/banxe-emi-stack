"""
services/device_fingerprint/fingerprint_models.py
Pydantic models for Device Fingerprinting (IL-DFP-01).
I-01: all risk scores as Decimal strings.
"""

from __future__ import annotations

from pydantic import BaseModel


class FingerprintData(BaseModel):
    user_agent: str
    screen_resolution: str = "1920x1080"
    timezone: str = "Europe/London"
    language: str = "en-GB"
    canvas_hash: str = ""
    webgl_hash: str = ""
    model_config = {"frozen": True}


class DeviceProfile(BaseModel):
    device_id: str
    customer_id: str
    fingerprint_hash: str
    user_agent: str
    registered_at: str
    model_config = {"frozen": True}


class MatchResult(BaseModel):
    customer_id: str
    match_type: str  # "known", "new", "suspicious"
    risk_score: str  # Decimal as string (I-01)
    device_id: str | None = None
    model_config = {"frozen": True}


class DeviceRiskScore(BaseModel):
    device_id: str
    score: str  # Decimal as string (I-01)
    reason: str
    model_config = {"frozen": True}
