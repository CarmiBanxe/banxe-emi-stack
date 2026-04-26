"""
services/customer_lifecycle/lifecycle_models.py
Customer lifecycle FSM models (IL-LCY-01).
States: prospect -> onboarding -> kyc_pending -> active -> dormant -> suspended -> closed -> offboarded
FCA SYSC 9: 5-year data retention after close.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CustomerState(str, Enum):
    PROSPECT = "prospect"
    ONBOARDING = "onboarding"
    KYC_PENDING = "kyc_pending"
    ACTIVE = "active"
    DORMANT = "dormant"
    SUSPENDED = "suspended"
    CLOSED = "closed"
    OFFBOARDED = "offboarded"


class LifecycleEvent(str, Enum):
    SUBMIT_APPLICATION = "submit_application"
    COMPLETE_KYC = "complete_kyc"
    ACTIVATE = "activate"
    FLAG_DORMANT = "flag_dormant"
    REACTIVATE = "reactivate"
    SUSPEND = "suspend"
    CLOSE = "close"
    OFFBOARD = "offboard"


class GuardCondition(BaseModel):
    name: str
    passed: bool
    reason: str = ""
    model_config = {"frozen": True}


class TransitionResult(BaseModel):
    customer_id: str
    from_state: CustomerState
    to_state: CustomerState
    event: LifecycleEvent
    guards_passed: list[GuardCondition]
    transitioned_at: str
    model_config = {"frozen": True}


class DormancyConfig(BaseModel):
    inactivity_days: int = 90
    model_config = {"frozen": True}


class RetentionConfig(BaseModel):
    years: int = 5  # FCA SYSC 9
    model_config = {"frozen": True}
