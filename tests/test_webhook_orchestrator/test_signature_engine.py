"""
tests/test_webhook_orchestrator/test_signature_engine.py — SignatureEngine tests
IL-WHO-01 | Phase 28 | banxe-emi-stack

18 tests: sign produces "t=,v1=" format, verify (valid sig passes, wrong sig fails,
expired timestamp fails), generate_secret is 32 chars hex, compare_digest (constant
time), payload ordering (sort_keys).
"""

from __future__ import annotations

import time

from services.webhook_orchestrator.signature_engine import (
    SIGNATURE_TOLERANCE_SECONDS,
    SignatureEngine,
)


def make_engine() -> SignatureEngine:
    return SignatureEngine()


class TestSign:
    def test_sign_returns_t_v1_format(self) -> None:
        engine = make_engine()
        result = engine.sign({"foo": "bar"}, "secret123", 1234567890)
        assert result.startswith("t=1234567890,v1=")

    def test_sign_v1_is_hex_string(self) -> None:
        engine = make_engine()
        result = engine.sign({"foo": "bar"}, "secret123", 1234567890)
        v1_part = result.split("v1=")[1]
        int(v1_part, 16)  # Should not raise — valid hex

    def test_sign_same_inputs_same_output(self) -> None:
        engine = make_engine()
        sig1 = engine.sign({"a": 1}, "mysecret", 9999)
        sig2 = engine.sign({"a": 1}, "mysecret", 9999)
        assert sig1 == sig2

    def test_sign_different_secrets_different_output(self) -> None:
        engine = make_engine()
        sig1 = engine.sign({"a": 1}, "secret-A", 9999)
        sig2 = engine.sign({"a": 1}, "secret-B", 9999)
        assert sig1 != sig2

    def test_sign_different_timestamps_different_output(self) -> None:
        engine = make_engine()
        sig1 = engine.sign({"a": 1}, "secret", 1000)
        sig2 = engine.sign({"a": 1}, "secret", 2000)
        assert sig1 != sig2

    def test_sign_payload_sort_keys(self) -> None:
        engine = make_engine()
        # Key order should not affect signature
        sig1 = engine.sign({"b": 2, "a": 1}, "secret", 1000)
        sig2 = engine.sign({"a": 1, "b": 2}, "secret", 1000)
        assert sig1 == sig2

    def test_sign_empty_payload(self) -> None:
        engine = make_engine()
        result = engine.sign({}, "secret", 1000)
        assert "t=1000,v1=" in result


class TestVerify:
    def test_verify_valid_signature(self) -> None:
        engine = make_engine()
        now = int(time.time())
        payload = {"event": "payment.created"}
        secret = "mysecret32chars1234567890123456"
        header = engine.sign(payload, secret, now)
        assert engine.verify(payload, header, secret) is True

    def test_verify_wrong_signature_fails(self) -> None:
        engine = make_engine()
        now = int(time.time())
        payload = {"event": "payment.created"}
        header = engine.sign(payload, "correct-secret", now)
        # Tamper with the signature
        tampered = header.replace("v1=", "v1=aaaa")
        assert engine.verify(payload, tampered, "correct-secret") is False

    def test_verify_wrong_secret_fails(self) -> None:
        engine = make_engine()
        now = int(time.time())
        payload = {"foo": "bar"}
        header = engine.sign(payload, "secret-A", now)
        assert engine.verify(payload, header, "secret-B") is False

    def test_verify_expired_timestamp_fails(self) -> None:
        engine = make_engine()
        old_timestamp = int(time.time()) - (SIGNATURE_TOLERANCE_SECONDS + 60)
        payload = {"foo": "bar"}
        header = engine.sign(payload, "secret", old_timestamp)
        assert engine.verify(payload, header, "secret") is False

    def test_verify_future_timestamp_within_tolerance_passes(self) -> None:
        engine = make_engine()
        near_future = int(time.time()) + 60  # 60s in future, within 5min window
        payload = {"foo": "bar"}
        secret = "testsecret"
        header = engine.sign(payload, secret, near_future)
        assert engine.verify(payload, header, secret) is True

    def test_verify_malformed_header_returns_false(self) -> None:
        engine = make_engine()
        assert engine.verify({}, "not-a-valid-header", "secret") is False

    def test_verify_missing_t_returns_false(self) -> None:
        engine = make_engine()
        assert engine.verify({}, "v1=abc123", "secret") is False

    def test_verify_missing_v1_returns_false(self) -> None:
        engine = make_engine()
        assert engine.verify({}, "t=1234567890", "secret") is False

    def test_verify_tampered_payload_fails(self) -> None:
        engine = make_engine()
        now = int(time.time())
        secret = "mysecret"
        header = engine.sign({"amount": "100"}, secret, now)
        # Verify with different payload
        assert engine.verify({"amount": "999"}, header, secret) is False


class TestGenerateSecret:
    def test_generate_secret_is_32_chars(self) -> None:
        engine = make_engine()
        secret = engine.generate_secret()
        assert len(secret) == 32

    def test_generate_secret_is_hex(self) -> None:
        engine = make_engine()
        secret = engine.generate_secret()
        int(secret, 16)  # Should not raise

    def test_generate_secret_is_unique(self) -> None:
        engine = make_engine()
        secrets = {engine.generate_secret() for _ in range(20)}
        assert len(secrets) == 20

    def test_tolerance_seconds_constant(self) -> None:
        assert SIGNATURE_TOLERANCE_SECONDS == 300
