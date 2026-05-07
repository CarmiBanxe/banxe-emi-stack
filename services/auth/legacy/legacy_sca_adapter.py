"""
legacy_sca_adapter.py — LegacyScaAdapter implements ScaServicePort (in-memory, REWRITE-2).

Semantic rewrite of AuthService SCA challenge lifecycle (banxe-common/auth.service.ts).
ECDH P-256 channel dropped — not portable to EMI Python stack; only OTP and TOTP mapped.
gRPC / Apollo transport dropped per ADR-025 §15-16.

Upstream TS method → ScaServicePort mapping:
  generateCode() + save()          → create_challenge(method="OTP")
  checkCode()                      → verify(method="OTP")
  ECDH challenge()                 → ScaApplicationError(code="method_not_supported")
  JWT issuance (signToken)         → ScaTokenIssuerPort.issue()

OUT OF SCOPE (separate concerns, not mapped):
  createApolloClient / gRPC calls  → infrastructure
  addCredentials after verify      → AuthApplicationService concern
  TOTP setup / confirm             → TwoFactorPort (ADR-015, Wave B Step 1)

Canon: ADR-015 + ADR-025 §15-16 + AUTH_IMPORT_ORDER + ScaServicePort
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import secrets

from services.auth.otp_delivery_port import OtpDeliveryPort
from services.auth.sca_application_service import ScaApplicationError
from services.auth.sca_models import SCAChallenge, SCAVerifyResult
from services.auth.sca_token_issuer_port import ScaTokenIssuerPort
from services.auth.two_factor_port import TwoFactorPort

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

_CHALLENGE_TTL_SECONDS: int = 300  # 5 min, PSD2 RTS Art.10
_MAX_ATTEMPTS: int = 5
_MAX_RESENDS: int = 3
_OTP_CHANNEL: str = "sms"
_SUPPORTED_METHODS: frozenset[str] = frozenset({"OTP", "TOTP"})

# ── Internal record ───────────────────────────────────────────────────────────


class _ChallengeRecord:
    """Mutable store entry for a live SCA challenge."""

    __slots__ = (
        "challenge",
        "otp_target",
        "otp_code",
        "locked",
    )

    def __init__(
        self,
        challenge: SCAChallenge,
        otp_target: str | None,
        otp_code: str | None,
    ) -> None:
        self.challenge = challenge
        self.otp_target = otp_target
        self.otp_code = otp_code
        self.locked = False


# ── Fake token issuer (default when none injected) ────────────────────────────


class _InMemoryTokenIssuer:
    def issue(self, challenge: SCAChallenge) -> str:
        return secrets.token_urlsafe(32)


# ── LegacyScaAdapter ─────────────────────────────────────────────────────────


class LegacyScaAdapter:
    """
    ScaServicePort implementation — semantic rewrite of SCA lifecycle (REWRITE-2).

    DI ports:
        otp_port     — OtpDeliveryPort (default: LegacyOtpAdapter)
        totp_adapter — TwoFactorPort   (default: LegacyTotpAdapter)
        token_issuer — ScaTokenIssuerPort (default: _InMemoryTokenIssuer)

    In-memory dict keyed by challenge_id. Not durable or concurrency-safe;
    acceptable for dev/test. Redis adapter (Wave C) handles durability.
    """

    def __init__(
        self,
        otp_port: OtpDeliveryPort,
        totp_adapter: TwoFactorPort,
        token_issuer: ScaTokenIssuerPort | None = None,
    ) -> None:
        self._otp = otp_port
        self._totp = totp_adapter
        self._issuer: ScaTokenIssuerPort = token_issuer or _InMemoryTokenIssuer()
        self._store: dict[str, _ChallengeRecord] = {}

    # ── ScaServicePort ────────────────────────────────────────────────────────

    def create_challenge(
        self,
        customer_id: str,
        transaction_id: str,
        method: str,
        amount: str | None = None,
        payee: str | None = None,
    ) -> SCAChallenge:
        method_upper = method.upper()
        if method_upper not in _SUPPORTED_METHODS:
            raise ScaApplicationError(
                f"SCA method '{method}' not supported by LegacyScaAdapter",
                code="method_not_supported",
            )

        challenge_id = secrets.token_urlsafe(16)
        now = datetime.now(UTC)
        challenge = SCAChallenge(
            challenge_id=challenge_id,
            customer_id=customer_id,
            transaction_id=transaction_id,
            method=method_upper,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=_CHALLENGE_TTL_SECONDS),
            amount=amount,
            payee=payee,
        )

        otp_target: str | None = None
        otp_code: str | None = None

        if method_upper == "OTP":
            otp_code = self._otp.generate_otp()
            otp_target = (
                customer_id  # target = customer_id; production adapter resolves phone/email
            )
            self._otp.send_otp(
                channel=_OTP_CHANNEL,
                target=otp_target,
                code=otp_code,
                ttl_seconds=_CHALLENGE_TTL_SECONDS,
            )

        self._store[challenge_id] = _ChallengeRecord(
            challenge=challenge,
            otp_target=otp_target,
            otp_code=otp_code,
        )
        logger.info(
            "SCA challenge created — id=%s customer=%s method=%s tx=%s",
            challenge_id,
            customer_id,
            method_upper,
            transaction_id,
        )
        return challenge

    def verify(
        self,
        challenge_id: str,
        otp_code: str | None = None,
        biometric_proof: str | None = None,
    ) -> SCAVerifyResult:
        record = self._store.get(challenge_id)
        if record is None:
            return SCAVerifyResult(verified=False, transaction_id="", error="challenge_not_found")

        ch = record.challenge

        if ch.status == "verified":
            return SCAVerifyResult(
                verified=False, transaction_id=ch.transaction_id, error="already_verified"
            )

        if datetime.now(UTC) > ch.expires_at:
            ch.status = "expired"
            return SCAVerifyResult(
                verified=False, transaction_id=ch.transaction_id, error="challenge_expired"
            )

        if record.locked:
            return SCAVerifyResult(
                verified=False,
                transaction_id=ch.transaction_id,
                error="locked",
                attempts_remaining=0,
            )

        ch.attempt_count += 1

        if ch.method == "OTP":
            result = self._otp.verify_otp(
                channel=_OTP_CHANNEL,
                target=record.otp_target or ch.customer_id,
                code=otp_code or "",
            )
            success = result.success
        elif ch.method == "TOTP":
            totp_result = self._totp.verify_totp(ch.customer_id, otp_code or "")
            success = totp_result.success
        else:  # pragma: no cover
            raise ScaApplicationError(
                f"Unsupported method in store: {ch.method}",
                code="method_not_supported",
            )

        if success:
            ch.status = "verified"
            sca_token = self._issuer.issue(ch)
            logger.info("SCA verified — id=%s tx=%s", challenge_id, ch.transaction_id)
            return SCAVerifyResult(
                verified=True,
                transaction_id=ch.transaction_id,
                sca_token=sca_token,
            )

        remaining = max(0, _MAX_ATTEMPTS - ch.attempt_count)
        if remaining == 0:
            record.locked = True
            ch.status = "locked"
            logger.warning("SCA locked — id=%s customer=%s", challenge_id, ch.customer_id)

        return SCAVerifyResult(
            verified=False,
            transaction_id=ch.transaction_id,
            error="invalid_code",
            attempts_remaining=remaining,
        )

    def resend_challenge(self, challenge_id: str) -> SCAChallenge:
        record = self._store.get(challenge_id)
        if record is None:
            raise ScaApplicationError("Challenge not found", code="challenge_not_found")

        ch = record.challenge

        if ch.status != "pending":
            raise ScaApplicationError(
                f"Cannot resend: challenge status is '{ch.status}'",
                code="resend_rejected",
            )

        if ch.resend_count >= _MAX_RESENDS:
            raise ScaApplicationError(
                "Resend limit reached",
                code="resend_limit_reached",
            )

        if ch.method != "OTP":
            raise ScaApplicationError(
                f"Resend not applicable for method '{ch.method}'",
                code="resend_not_applicable",
            )

        ch.resend_count += 1
        new_code = self._otp.generate_otp()
        record.otp_code = new_code
        target = record.otp_target or ch.customer_id
        self._otp.send_otp(
            channel=_OTP_CHANNEL,
            target=target,
            code=new_code,
            ttl_seconds=_CHALLENGE_TTL_SECONDS,
        )
        logger.info("SCA OTP resent — id=%s resend_count=%d", challenge_id, ch.resend_count)
        return ch

    def list_methods(self, customer_id: str) -> list[str]:  # noqa: ARG002
        """Return supported SCA methods (OTP always available; TOTP if enabled)."""
        return sorted(_SUPPORTED_METHODS)
