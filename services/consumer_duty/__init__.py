"""
services/consumer_duty/__init__.py
Consumer Duty Outcome Monitoring — Public API (Phase 50)
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 Consumer Duty, FCA FG21/1, FCA PROD, FCA COBS 2.1, FCA PRIN 12
"""

from __future__ import annotations

# Phase 50 exports (IL-CDO-01)
from services.consumer_duty.consumer_duty_agent import ConsumerDutyAgent

# Legacy Phase 9 exports (backward compatibility)
from services.consumer_duty.consumer_duty_port import (
    ConsumerDutyOutcome,
    ConsumerDutyReport,
    FairValueAssessment,
    FairValueVerdict,
    OutcomeRating,
    OutcomeRecord,
)
from services.consumer_duty.consumer_duty_reporter import ConsumerDutyReporter
from services.consumer_duty.consumer_duty_service import ConsumerDutyService
from services.consumer_duty.consumer_support_tracker import ConsumerSupportTracker
from services.consumer_duty.models_v2 import (
    AssessmentStatus,
    ConsumerProfile,
    HITLProposal,
    InMemoryOutcomeStore,
    InMemoryProductGovernance,
    InMemoryVulnerabilityAlertStore,
    InterventionType,
    OutcomeAssessment,
    OutcomeStorePort,
    OutcomeType,
    ProductGovernancePort,
    ProductGovernanceRecord,
    VulnerabilityAlert,
    VulnerabilityAlertPort,
    VulnerabilityFlag,
)
from services.consumer_duty.outcome_assessor import OutcomeAssessor
from services.consumer_duty.product_governance import ProductGovernanceService
from services.consumer_duty.vulnerability_detector import VulnerabilityDetector

__all__ = [
    # Legacy (Phase 9)
    "ConsumerDutyService",
    "ConsumerDutyOutcome",
    "ConsumerDutyReport",
    "FairValueAssessment",
    "FairValueVerdict",
    "OutcomeRating",
    "OutcomeRecord",
    # Phase 50 models
    "OutcomeType",
    "VulnerabilityFlag",
    "InterventionType",
    "AssessmentStatus",
    "ConsumerProfile",
    "OutcomeAssessment",
    "ProductGovernanceRecord",
    "VulnerabilityAlert",
    "HITLProposal",
    # Protocols
    "OutcomeStorePort",
    "ProductGovernancePort",
    "VulnerabilityAlertPort",
    # InMemory stubs
    "InMemoryOutcomeStore",
    "InMemoryProductGovernance",
    "InMemoryVulnerabilityAlertStore",
    # Services
    "OutcomeAssessor",
    "VulnerabilityDetector",
    "ProductGovernanceService",
    "ConsumerSupportTracker",
    "ConsumerDutyReporter",
    "ConsumerDutyAgent",
]
