"""
api/routers/device_fingerprint.py — Device Fingerprint endpoints
IL-DFP-01 | banxe-emi-stack
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.device_fingerprint.fingerprint_agent import DeviceHITLProposal, FingerprintAgent
from services.device_fingerprint.fingerprint_engine import FingerprintEngine
from services.device_fingerprint.fingerprint_models import FingerprintData

logger = logging.getLogger("banxe.device_fingerprint")
router = APIRouter(tags=["DeviceFingerprint"])

_engine = FingerprintEngine()
_agent = FingerprintAgent(_engine)


class RegisterDeviceRequest(BaseModel):
    customer_id: str
    fingerprint: FingerprintData


class MatchDeviceRequest(BaseModel):
    customer_id: str
    fingerprint: FingerprintData


@router.post("/devices/register", status_code=201, summary="Register device fingerprint")
async def register_device(body: RegisterDeviceRequest):  # type: ignore[return]
    profile = _engine.register_device(body.customer_id, body.fingerprint)
    return {
        "device_id": profile.device_id,
        "customer_id": profile.customer_id,
        "registered_at": profile.registered_at,
    }


@router.post("/devices/match", summary="Match device fingerprint (I-27 HITL for suspicious)")
async def match_device(body: MatchDeviceRequest):  # type: ignore[return]
    result = _agent.assess_device(body.customer_id, body.fingerprint)
    if isinstance(result, DeviceHITLProposal):
        return {
            "status": "HITL_REQUIRED",
            "proposal_id": result.proposal_id,
            "match_type": result.match_type,
            "risk_score": result.risk_score,
            "requires_approval_from": result.requires_approval_from,
        }
    return {
        "customer_id": result.customer_id,
        "match_type": result.match_type,
        "risk_score": result.risk_score,
        "device_id": result.device_id,
    }


@router.get("/devices/{customer_id}", summary="List customer devices")
async def list_customer_devices(customer_id: str):  # type: ignore[return]
    devices = _engine._store.get_by_customer(customer_id)
    return {
        "customer_id": customer_id,
        "device_count": len(devices),
        "devices": [{"device_id": d.device_id, "registered_at": d.registered_at} for d in devices],
    }
