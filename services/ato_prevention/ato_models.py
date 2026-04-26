"""
services/ato_prevention/ato_models.py
Pydantic models for ATO Prevention (IL-ATO-01).
I-01: risk_score as Decimal string.
"""

from __future__ import annotations

from pydantic import BaseModel


class GeoLocation(BaseModel):
    country: str
    city: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    model_config = {"frozen": True}


class LoginAttempt(BaseModel):
    customer_id: str
    ip_address: str
    device_fingerprint: str  # hash string
    geo: GeoLocation
    success: bool = True
    model_config = {"frozen": True}


class ImpossibleTravelResult(BaseModel):
    detected: bool
    distance_km: float
    time_delta_hours: float
    model_config = {"frozen": True}


class ATOAssessment(BaseModel):
    customer_id: str
    risk_score: str  # Decimal as string (I-01)
    signals: list[str]
    action: str  # "allow", "challenge", "lock"
    model_config = {"frozen": True}
