"""
services/webhook_orchestrator/signature_engine.py — HMAC-SHA256 Signature Engine
IL-WHO-01 | Phase 28 | banxe-emi-stack

Signs and verifies webhook payloads using HMAC-SHA256. Provides replay protection
via 5-minute timestamp tolerance window (I-12, GDPR Art.32).
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import time
import uuid

SIGNATURE_TOLERANCE_SECONDS: int = 300  # 5 minutes


@dataclass
class SignatureEngine:
    """HMAC-SHA256 signing and verification for webhook deliveries.

    Signature format: t={timestamp},v1={hex_signature}
    Replay protection: timestamp must be within SIGNATURE_TOLERANCE_SECONDS of now.
    """

    def sign(self, payload: dict, secret: str, timestamp: int) -> str:
        """Sign a payload with HMAC-SHA256 and return the signature header value.

        Args:
            payload: The webhook event payload dict.
            secret: The subscription HMAC secret.
            timestamp: Unix timestamp (seconds since epoch).

        Returns:
            Signature header string: "t={timestamp},v1={hex_signature}"
        """
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        message = f"{timestamp}.{payload_str}"
        signature = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={signature}"

    def verify(
        self,
        payload: dict,
        signature_header: str,
        secret: str,
    ) -> bool:
        """Verify a webhook signature header.

        Checks:
        1. Header can be parsed for t= and v1= components.
        2. Timestamp is within SIGNATURE_TOLERANCE_SECONDS of current time.
        3. Recomputed signature matches using hmac.compare_digest (constant-time).

        Returns True if valid, False otherwise.
        """
        try:
            parts = dict(part.split("=", 1) for part in signature_header.split(","))
            timestamp_str = parts.get("t", "")
            received_sig = parts.get("v1", "")
            if not timestamp_str or not received_sig:
                return False

            timestamp = int(timestamp_str)
        except (ValueError, AttributeError):
            return False

        # Replay protection: reject timestamps outside tolerance window
        now = int(time.time())
        if abs(now - timestamp) > SIGNATURE_TOLERANCE_SECONDS:
            return False

        # Recompute and compare constant-time
        payload_str = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        message = f"{timestamp}.{payload_str}"
        expected_sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

        return hmac.compare_digest(expected_sig, received_sig)

    def generate_secret(self) -> str:
        """Generate a new 32-char hex HMAC secret."""
        return hashlib.sha256(uuid.uuid4().hex.encode()).hexdigest()[:32]
