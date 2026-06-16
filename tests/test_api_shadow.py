"""
tests/test_api_shadow.py — FU-2 Phase 8 production shadow-mode at the HTTP boundary.

Proves the two banking-safe properties of the prod entrypoint wiring through the real
FastAPI app:

  * **Flag off (default):** no shadow log/metric is emitted — the mirror is a pure no-op.
  * **Flag on in a simulated prod env (sampled):** the SAME live response is returned
    (status + business fields unchanged) AND a shadow comparison is logged. The live path
    is never altered by, nor dependent on, the shadow mirror.

The shadow descriptor is a non-PII endpoint label, so nothing here exercises user content.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_TICKET = {
    "customer_id": "cust-shadow-001",
    "subject": "Question about my statement",
    "body": "I would like to understand a line item on my latest statement please",
}


def _create_ticket() -> dict:
    resp = client.post("/v1/support/tickets", json=_TICKET)
    assert resp.status_code == 201
    return resp.json()


def test_shadow_off_by_default_emits_nothing(caplog):
    with caplog.at_level(logging.INFO, logger="banxe.intent_layer.shadow"):
        body = _create_ticket()
    # Live response is well-formed and the shadow logger stayed silent.
    assert body["id"]
    assert "intent_layer.shadow" not in caplog.text


def test_shadow_on_in_prod_leaves_live_response_unchanged_and_logs(monkeypatch, caplog):
    monkeypatch.setenv("INTENT_LAYER_SHADOW_ENABLED_PROD", "true")
    monkeypatch.setenv("BANXE_ENV", "production")
    monkeypatch.setenv("INTENT_LAYER_SHADOW_SAMPLE_PCT", "100")  # force the slice

    with caplog.at_level(logging.INFO, logger="banxe.intent_layer.shadow"):
        body = _create_ticket()

    # Live business outcome is unchanged: same 201, same response contract.
    assert body["id"]
    assert body["customer_id"] == "cust-shadow-001"
    assert "auto_resolved" in body and "is_formal_complaint" in body
    # The shadow mirror ran and recorded the baseline-vs-shadow comparison.
    assert "intent_layer.shadow" in caplog.text
    assert "mode=shadow" in caplog.text
    # Support has no canonical IL intent → a governance event, i.e. a baseline mismatch.
    assert "baseline_capability=Support" in caplog.text


def test_shadow_failure_never_breaks_the_live_endpoint(monkeypatch):
    # Even if the shadow pipeline itself raised, the endpoint must still serve. Force the
    # slice and point the metrics sink at an invalid value (get_shadow_metrics raises);
    # the mirror swallows it, so the ticket is still created.
    monkeypatch.setenv("INTENT_LAYER_SHADOW_ENABLED_PROD", "true")
    monkeypatch.setenv("BANXE_ENV", "production")
    monkeypatch.setenv("INTENT_LAYER_SHADOW_SAMPLE_PCT", "100")
    monkeypatch.setenv("CANARY_METRICS", "not-a-valid-sink")
    resp = client.post("/v1/support/tickets", json=_TICKET)
    assert resp.status_code == 201
