"""
services/auth/sca_service.py — PSD2 SCA Challenge Service
S15-01 | PSD2 Directive 2015/2366 Art.97 | banxe-emi-stack

Strong Customer Authentication for:
  - Payments > £30 (PSR 2017 Reg.71)
  - Sensitive profile changes
  - Login from new device

PSD2 RTS Art.10 Dynamic Linking:
  - SCA token contains { txn_id, amount, payee } — bound to specific transaction
  - Token TTL: max 300 seconds (PSD2 RTS Art.4)

Two-factor requirements (PSD2 Art.4(30)):
  - OTP method: TOTP (knowledge + possession)
  - Biometric method: possession + inherence (expo-local-auth / WebAuthn)

Replay prevention:
  - challenge_id is one-time use; marked USED after verify
  - Concurrent challenges per customer: max 3 active

Rate limiting:
  - Max 5 failed verifications per challenge → 429
  - After 5 failures: challenge locked, customer must request new one
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import logging
import os
import uuid

from services.auth.sca_models import SCAChallenge, SCAMethods, SCAVerifyResult
from services.auth.sca_token_issuer import JwtScaTokenIssuer
from services.auth.sca_token_issuer_port import ScaTokenIssuerPort

logger = logging.getLogger("banxe.sca")

# ── Config ────────────────────────────────────────────────────────────────────

SCA_CHALLENGE_TTL_SEC = int(os.environ.get("SCA_CHALLENGE_TTL_SEC", "120"))  # 2 min
SCA_MAX_ATTEMPTS = int(os.environ.get("SCA_MAX_ATTEMPTS", "5"))
SCA_MAX_CONCURRENT = int(os.environ.get("SCA_MAX_CONCURRENT", "3"))
SCA_MAX_RESENDS = int(os.environ.get("SCA_MAX_RESENDS", "3"))  # PSD2 Art.97 resend cap
SCA_SECRET_KEY = os.environ.get("SCA_SECRET_KEY", "dev-sca-secret-change-in-prod")

# Known biometric proof prefix (production: cryptographic assertion)
_BIOMETRIC_PROOF_PREFIX = "biometric:approved:"

SCA_ALGORITHM = "HS256"  # backward-compat export for tests/importers


# ── InMemory Store ────────────────────────────────────────────────────────────


class InMemorySCAStore:
    """
    In-memory SCA challenge store.
    Production: replace with Redis (TTL-backed) or PostgreSQL.

    Thread-safety: not thread-safe for high-concurrency production use.
    For production: use Redis SETNX for challenge creation (atomic).
    """

    def __init__(self) -> None:
        self._challenges: dict[str, SCAChallenge] = {}

    def save(self, challenge: SCAChallenge) -> None:
        self._challenges[challenge.challenge_id] = challenge

    def get(self, challenge_id: str) -> SCAChallenge | None:
        return self._challenges.get(challenge_id)

    def get_active_for_customer(self, customer_id: str) -> list[SCAChallenge]:
        now = datetime.now(tz=UTC)
        return [
            c
            for c in self._challenges.values()
            if c.customer_id == customer_id and c.status == "pending" and c.expires_at > now
        ]

    def count_active_for_customer(self, customer_id: str) -> int:
        return len(self.get_active_for_customer(customer_id))

    def delete(self, challenge_id: str) -> None:
        self._challenges.pop(challenge_id, None)


# ── SCA Service ───────────────────────────────────────────────────────────────


class SCAService:
    """
    PSD2 SCA challenge + verification service.

    OTP flow:
      1. create_challenge(customer_id, txn_id, method="otp") → challenge_id
      2. Customer enters TOTP code from authenticator app
      3. verify(challenge_id, otp_code=code) → SCAVerifyResult

    Biometric flow:
      1. create_challenge(customer_id, txn_id, method="biometric") → challenge_id
      2. Device performs biometric auth → returns biometric_proof string
      3. verify(challenge_id, biometric_proof=proof) → SCAVerifyResult

    Dynamic linking (PSD2 RTS Art.10):
      - SCA token JWT contains { txn_id, amount, payee } — binds auth to transaction
      - Token TTL: 300 sec maximum
    """

    def __init__(
        self,
        store: InMemorySCAStore | None = None,
        token_issuer: ScaTokenIssuerPort | None = None,
    ) -> None:
        self._store = store or InMemorySCAStore()
        self._token_issuer: ScaTokenIssuerPort = token_issuer or JwtScaTokenIssuer()
        # OTP secrets per customer (mirroring TOTPService pattern)
        # In production: read from TOTPService/Redis
        self._otp_secrets: dict[str, str] = {}

    def create_challenge(
        self,
        customer_id: str,
        transaction_id: str,
        method: str,
        amount: str | None = None,
        payee: str | None = None,
    ) -> SCAChallenge:
        """
        Initiate a new SCA challenge.

        Raises:
            ValueError: if method is not "otp" or "biometric"
            RuntimeError: if customer has >= SCA_MAX_CONCURRENT active challenges
        """
        if method not in ("otp", "biometric"):
            raise ValueError(f"Unsupported SCA method: {method!r}. Use 'otp' or 'biometric'.")

        # Check concurrent challenge limit
        active_count = self._store.count_active_for_customer(customer_id)
        if active_count >= SCA_MAX_CONCURRENT:
            raise RuntimeError(
                f"Customer {customer_id!r} has {active_count} active SCA challenges "
                f"(max {SCA_MAX_CONCURRENT}). Complete or expire existing challenges first."
            )

        now = datetime.now(tz=UTC)
        challenge = SCAChallenge(
            challenge_id=str(uuid.uuid4()),
            customer_id=customer_id,
            transaction_id=transaction_id,
            method=method,
            status="pending",
            created_at=now,
            expires_at=now + timedelta(seconds=SCA_CHALLENGE_TTL_SEC),
            amount=amount,
            payee=payee,
        )
        self._store.save(challenge)
        logger.info(
            "sca.challenge_created challenge_id=%s customer=%s method=%s txn=%s",
            challenge.challenge_id,
            customer_id,
            method,
            transaction_id,
        )
        return challenge

    def verify(
        self,
        challenge_id: str,
        otp_code: str | None = None,
        biometric_proof: str | None = None,
    ) -> SCAVerifyResult:
        """
        Verify an SCA challenge.

        Returns SCAVerifyResult with:
          - verified=True + sca_token if successful
          - verified=False + error + attempts_remaining if failed

        Replay prevention: challenge marked "used" after success.
        Rate limiting: challenge locked after SCA_MAX_ATTEMPTS failures.
        """
        challenge = self._store.get(challenge_id)

        if challenge is None:
            return SCAVerifyResult(
                verified=False,
                transaction_id="",
                error="Challenge not found",
            )

        # Check expiry
        if datetime.now(tz=UTC) > challenge.expires_at:
            challenge.status = "expired"
            self._store.save(challenge)
            return SCAVerifyResult(
                verified=False,
                transaction_id=challenge.transaction_id,
                error="Challenge expired",
            )

        # Check already used
        if challenge.status == "used":
            return SCAVerifyResult(
                verified=False,
                transaction_id=challenge.transaction_id,
                error="Challenge already used",
            )

        # Check rate limit
        if challenge.status == "failed" or challenge.attempt_count >= SCA_MAX_ATTEMPTS:
            return SCAVerifyResult(
                verified=False,
                transaction_id=challenge.transaction_id,
                error="Too many failed attempts. Request a new challenge.",
                attempts_remaining=0,
            )

        # Verify based on method
        verified = False
        if challenge.method == "otp":
            verified = self._verify_otp(challenge, otp_code or "")
        elif challenge.method == "biometric":
            verified = self._verify_biometric(challenge, biometric_proof or "")

        # Update attempt counter
        challenge.attempt_count += 1

        if verified:
            challenge.status = "used"
            self._store.save(challenge)
            token = self._issue_sca_token(challenge)
            logger.info(
                "sca.verified challenge_id=%s customer=%s txn=%s",
                challenge_id,
                challenge.customer_id,
                challenge.transaction_id,
            )
            return SCAVerifyResult(
                verified=True,
                transaction_id=challenge.transaction_id,
                sca_token=token,
            )
        else:
            remaining = max(0, SCA_MAX_ATTEMPTS - challenge.attempt_count)
            if remaining == 0:
                challenge.status = "failed"
            self._store.save(challenge)
            logger.warning(
                "sca.verify_failed challenge_id=%s attempt=%d remaining=%d",
                challenge_id,
                challenge.attempt_count,
                remaining,
            )
            return SCAVerifyResult(
                verified=False,
                transaction_id=challenge.transaction_id,
                error="Invalid OTP or biometric proof",
                attempts_remaining=remaining,
            )

    def get_methods(self, customer_id: str) -> SCAMethods:
        """
        Return available SCA methods for a customer.
        Currently all customers support OTP; biometric if enrolled.
        """
        methods = ["otp"]
        preferred = "otp"

        # Biometric: check if customer has biometric enrolled
        # In production: check device enrollment records
        # For now: customer_id ending in "-bio" = biometric enrolled (test hook)
        if customer_id.endswith("-bio") or customer_id in self._otp_secrets:
            methods = ["biometric", "otp"]
            preferred = "biometric"

        return SCAMethods(
            customer_id=customer_id,
            methods=methods,
            preferred=preferred,
        )

    def resend_challenge(self, challenge_id: str) -> SCAChallenge:
        """
        Resend an existing SCA challenge: reset TTL and increment resend counter.

        PSD2 Art.97 — customers may request a new OTP if the previous one expired or
        was not received.  Rate-limited to SCA_MAX_RESENDS per challenge_id.

        Raises:
            KeyError: if challenge_id does not exist
            ValueError: if challenge is already used, failed, or resend limit exceeded
        """
        challenge = self._store.get(challenge_id)
        if challenge is None:
            raise KeyError(f"Challenge {challenge_id!r} not found")

        if challenge.status in ("used", "failed"):
            raise ValueError(
                f"Challenge {challenge_id!r} is {challenge.status!r} and cannot be resent. "
                "Request a new challenge."
            )

        if challenge.resend_count >= SCA_MAX_RESENDS:
            raise ValueError(
                f"Resend limit reached ({SCA_MAX_RESENDS}) for challenge {challenge_id!r}. "
                "Request a new challenge."
            )

        now = datetime.now(tz=UTC)
        challenge.expires_at = now + timedelta(seconds=SCA_CHALLENGE_TTL_SEC)
        challenge.status = "pending"
        challenge.resend_count += 1
        self._store.save(challenge)

        logger.info(
            "sca.challenge_resent challenge_id=%s customer=%s resend=%d",
            challenge_id,
            challenge.customer_id,
            challenge.resend_count,
        )
        return challenge

    def register_otp_secret(self, customer_id: str, secret: str) -> None:
        """Register a TOTP secret for a customer (used by TOTPService integration)."""
        self._otp_secrets[customer_id] = secret

    # ── Internal ──────────────────────────────────────────────────────────────

    def _verify_otp(self, challenge: SCAChallenge, otp_code: str) -> bool:
        """Verify TOTP code against stored secret."""
        try:
            import pyotp
        except ImportError:
            # Fallback without pyotp: accept any 6-digit code matching test hook
            return otp_code == "000000" and challenge.customer_id.endswith("-test")

        secret = self._otp_secrets.get(challenge.customer_id)
        if not secret:
            # No secret registered → derive deterministic test secret from customer_id
            # In production: always require prior TOTP enrollment
            derived = hmac.new(
                SCA_SECRET_KEY.encode(),
                challenge.customer_id.encode(),
                hashlib.sha256,
            ).hexdigest()[:32]
            import base64

            secret = base64.b32encode(derived.encode()).decode()[:32]
            self._otp_secrets[challenge.customer_id] = secret

        from services.auth.two_factor import TOTP_DIGITS, TOTP_INTERVAL, TOTP_VALID_WINDOW

        totp = pyotp.TOTP(secret, digits=TOTP_DIGITS, interval=TOTP_INTERVAL)
        return totp.verify(otp_code.strip(), valid_window=TOTP_VALID_WINDOW)

    def _verify_biometric(self, challenge: SCAChallenge, biometric_proof: str) -> bool:
        """
        Verify biometric proof.

        Production: validate FIDO2/WebAuthn assertion (signature over challenge nonce).
        Stub: accept any proof starting with 'biometric:approved:' prefix.
        """
        return biometric_proof.startswith(_BIOMETRIC_PROOF_PREFIX)

    def _issue_sca_token(self, challenge: SCAChallenge) -> str:
        """Delegate PSD2 RTS Art.10 dynamic-linking SCA token issuance to ScaTokenIssuerPort."""
        return self._token_issuer.issue(challenge)


# ── Factory ───────────────────────────────────────────────────────────────────

_sca_service: SCAService | None = None


def get_sca_service() -> SCAService:
    """
    Service factory — returns singleton SCAService.
    Production: pass Redis-backed store via env var SCA_STORE=redis.
    """
    global _sca_service  # noqa: PLW0603
    if _sca_service is None:
        _sca_service = SCAService()
    return _sca_service
