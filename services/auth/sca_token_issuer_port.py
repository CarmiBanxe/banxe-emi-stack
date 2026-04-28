"""ScaTokenIssuerPort — hexagonal port for PSD2 RTS Art.10 SCA token issuance."""

from __future__ import annotations

from typing import Protocol

from services.auth.sca_models import SCAChallenge


class ScaTokenIssuerPort(Protocol):
    def issue(self, challenge: SCAChallenge) -> str: ...
