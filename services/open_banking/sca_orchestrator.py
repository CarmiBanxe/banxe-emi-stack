"""
services/open_banking/sca_orchestrator.py
IL-OBK-01 | Phase 15

Strong Customer Authentication orchestration (PSD2 RTS Art.4)
Supports redirect / decoupled / embedded flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import uuid

from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    Consent,
    FlowType,
    OBAuditTrailPort,
    _new_event,
)

_SCA_EXPIRY_MINUTES = 10


@dataclass
class SCAChallenge:
    """Represents an in-flight SCA challenge."""

    id: str
    consent_id: str
    flow_type: FlowType
    redirect_url: str | None
    otp_hint: str | None
    expires_at: datetime
    completed: bool = False


class SCAOrchestrator:
    """Orchestrates PSD2 RTS Art.4 Strong Customer Authentication flows."""

    def __init__(
        self,
        consent_manager: ConsentManager,
        audit: OBAuditTrailPort,
    ) -> None:
        self._consent_manager = consent_manager
        self._audit = audit
        self._challenges: dict[str, SCAChallenge] = {}

    async def initiate_sca(
        self,
        consent_id: str,
        flow_type: FlowType,
        actor: str,
    ) -> SCAChallenge:
        """Initiate a new SCA challenge for the given consent.

        Creates a 10-minute expiry challenge.  For REDIRECT flow a redirect_url
        is generated; for DECOUPLED an otp_hint is set.
        """
        consent = await self._consent_manager.get_consent(consent_id)
        if consent is None:
            raise ValueError(f"Consent not found: {consent_id}")

        challenge_id = str(uuid.uuid4())
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=_SCA_EXPIRY_MINUTES)

        redirect_url: str | None = None
        otp_hint: str | None = None

        if flow_type == FlowType.REDIRECT:
            redirect_url = (
                f"https://auth.banxe.com/sca/redirect?challenge={challenge_id}&consent={consent_id}"
            )
        elif flow_type == FlowType.DECOUPLED:
            otp_hint = f"OTP sent to registered device (hint: ***{challenge_id[-4:]})"

        challenge = SCAChallenge(
            id=challenge_id,
            consent_id=consent_id,
            flow_type=flow_type,
            redirect_url=redirect_url,
            otp_hint=otp_hint,
            expires_at=expires_at,
        )
        self._challenges[challenge_id] = challenge

        await self._audit.append(
            _new_event(
                event_type="sca.initiated",
                entity_id=consent.entity_id,
                actor=actor,
                consent_id=consent_id,
                details={
                    "challenge_id": challenge_id,
                    "flow_type": flow_type.value,
                    "expires_at": expires_at.isoformat(),
                },
            )
        )
        return challenge

    async def complete_sca(
        self,
        challenge_id: str,
        auth_code: str,
        actor: str,
    ) -> Consent:
        """Complete SCA: validate challenge, authorise consent.

        Raises ValueError if challenge not found or expired.
        """
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            raise ValueError(f"SCA challenge not found: {challenge_id}")

        if challenge.completed:
            raise ValueError(f"SCA challenge already completed: {challenge_id}")

        if datetime.now(UTC) >= challenge.expires_at:
            raise ValueError(f"SCA challenge expired: {challenge_id}")

        consent = await self._consent_manager.authorise_consent(
            challenge.consent_id,
            auth_code,
            actor,
        )

        self._challenges[challenge_id] = SCAChallenge(
            id=challenge.id,
            consent_id=challenge.consent_id,
            flow_type=challenge.flow_type,
            redirect_url=challenge.redirect_url,
            otp_hint=challenge.otp_hint,
            expires_at=challenge.expires_at,
            completed=True,
        )

        await self._audit.append(
            _new_event(
                event_type="sca.completed",
                entity_id=consent.entity_id,
                actor=actor,
                consent_id=challenge.consent_id,
                details={"challenge_id": challenge_id},
            )
        )
        return consent

    async def get_challenge(self, challenge_id: str) -> SCAChallenge | None:
        """Retrieve a challenge by ID."""
        return self._challenges.get(challenge_id)
