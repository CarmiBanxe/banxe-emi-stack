"""KYC factory — DI singletons for KYC audit emitter (ADR-028 Step 4).

get_kyc_retrigger_audit_emitter() resolves a shared KycRetriggerAuditEmitter
bound to the singleton BufferedAuditPort from api.deps so re-verification
audit events flow into the same SQLite ring buffer the drain cron consumes.
"""

from __future__ import annotations

from functools import lru_cache

from services.kyc.kyc_retrigger_audit_emitter import KycRetriggerAuditEmitter


@lru_cache(maxsize=1)
def get_kyc_retrigger_audit_emitter() -> KycRetriggerAuditEmitter:
    """Singleton KycRetriggerAuditEmitter wired to the shared ADR-027
    BufferedAuditPort singleton (api.deps.get_buffered_audit_port).

    Lazy-imports api.deps so callers that never need the emitter don't pay
    the api.deps top-level import cost.
    """
    from api.deps import get_buffered_audit_port

    return KycRetriggerAuditEmitter(audit_port=get_buffered_audit_port())
