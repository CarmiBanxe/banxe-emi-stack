"""
services/consent_management/__init__.py
Consent Management & TPP Registry — Public API
IL-CNS-01 | Phase 49 | Sprint 35

FCA: PSD2 Art.65-67, RTS on SCA Art.29-32, FCA PERG 15.5, PSR 2017 Reg.112-120
"""

from __future__ import annotations

from services.consent_management.consent_agent import ConsentAgent
from services.consent_management.consent_engine import ConsentEngine
from services.consent_management.consent_validator import ConsentValidator
from services.consent_management.models import (
    BLOCKED_JURISDICTIONS,
    AuditLogPort,
    ConsentAuditEvent,
    ConsentGrant,
    ConsentScope,
    ConsentStatus,
    ConsentStorePort,
    ConsentType,
    HITLProposal,
    InMemoryAuditLog,
    InMemoryConsentStore,
    InMemoryTPPRegistry,
    TPPRegistration,
    TPPRegistryPort,
    TPPStatus,
    TPPType,
)
from services.consent_management.psd2_flow_handler import PSD2FlowHandler
from services.consent_management.tpp_registry import TPPRegistryService

__all__ = [
    # Models
    "BLOCKED_JURISDICTIONS",
    "ConsentGrant",
    "ConsentType",
    "ConsentStatus",
    "ConsentScope",
    "TPPRegistration",
    "TPPType",
    "TPPStatus",
    "ConsentAuditEvent",
    "HITLProposal",
    # Protocols
    "ConsentStorePort",
    "TPPRegistryPort",
    "AuditLogPort",
    # InMemory stubs
    "InMemoryConsentStore",
    "InMemoryTPPRegistry",
    "InMemoryAuditLog",
    # Services
    "ConsentEngine",
    "ConsentValidator",
    "TPPRegistryService",
    "PSD2FlowHandler",
    "ConsentAgent",
]
