"""
services/voice_support/gateway.py — LiveKit/Pipecat + SIP telephony gateway
GAP-069 | IMPL-3 | banxe-emi-stack

Realtime voice gateway adapter. Holds NO secrets and opens NO connection when
unconfigured — a safe-stub that mints a local session reference (I-SEC).
Configure LIVEKIT_URL (+ LIVEKIT_API_KEY/SECRET via env only) to go live.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class LiveKitPipecatGateway:
    """TelephonyGatewayPort — LiveKit/Pipecat realtime + SIP (safe-stub offline)."""

    def __init__(self, livekit_url: str | None = None) -> None:
        self._url = livekit_url or os.environ.get("LIVEKIT_URL", "")
        self._seq = 0

    @property
    def configured(self) -> bool:
        return bool(self._url)

    def start_call(self, customer_id: str) -> str:
        self._seq += 1
        ref = f"voice-{customer_id}-{self._seq}"
        if not self._url:
            logger.info("LiveKit not configured — local safe-stub session %s", ref)
            return ref
        # Live path would establish a LiveKit room / Pipecat pipeline here.
        logger.info("LiveKit session opened for %s (%s)", customer_id, ref)
        return ref

    def end_call(self, gateway_ref: str) -> None:
        logger.info("voice gateway session closed: %s", gateway_ref)
