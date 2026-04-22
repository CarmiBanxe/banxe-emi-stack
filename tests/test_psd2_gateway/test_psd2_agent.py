"""Tests for PSD2Agent — create_consent → HITLProposal, configure_auto_pull → HITLProposal.

IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.psd2_gateway.adorsys_client import AdorsysClient
from services.psd2_gateway.camt053_auto_pull import AutoPuller
from services.psd2_gateway.psd2_agent import PSD2Agent
from services.psd2_gateway.psd2_models import (
    ConsentRequest,
    InMemoryConsentStore,
    InMemoryTransactionStore,
)

_GB_IBAN = "GB29NWBK60161331926819"
_DE_IBAN = "DE89370400440532013000"
_VALID_UNTIL = "2027-01-01"
_OPS_EMAIL = "ops@banxe.com"
_DATE_FROM = "2026-01-01"
_DATE_TO = "2026-01-31"


def _make_agent() -> PSD2Agent:
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    puller = AutoPuller()
    agent = PSD2Agent(client=client, puller=puller)
    # Replace agent's internal consent store to match client's
    agent._consent_store = consent_store
    return agent


def _consent_proposal(agent: PSD2Agent) -> dict:
    return agent.create_consent_proposal(_GB_IBAN, "allAccounts", _VALID_UNTIL, _OPS_EMAIL)


def _req() -> ConsentRequest:
    return ConsentRequest(iban=_GB_IBAN, access_type="allAccounts", valid_until=_VALID_UNTIL)


# ── create_consent_proposal (I-27 HITL L4) ────────────────────────────────


def test_create_consent_proposal_hitl_type() -> None:
    """I-27: create_consent must return HITLProposal."""
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert proposal["proposal_type"] == "HITL_REQUIRED"


def test_create_consent_proposal_l4_autonomy() -> None:
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert proposal["autonomy_level"] == "L4"


def test_create_consent_proposal_compliance_officer() -> None:
    """I-27: Consent requires COMPLIANCE_OFFICER."""
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert proposal["requires_approval_from"] == "COMPLIANCE_OFFICER"


def test_create_consent_proposal_action_field() -> None:
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert proposal["action"] == "create_psd2_consent"


def test_create_consent_proposal_masks_iban() -> None:
    """No PII: IBAN in proposal must be masked."""
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    iban_in_data = proposal["data"]["iban"]
    assert iban_in_data.endswith("***")
    assert "GB29NW" in iban_in_data  # first 6 OK


def test_create_consent_proposal_has_created_at() -> None:
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert "created_at" in proposal
    assert "T" in proposal["created_at"]


def test_create_consent_proposal_has_proposal_id() -> None:
    agent = _make_agent()
    proposal = _consent_proposal(agent)
    assert "proposal_id" in proposal
    assert proposal["proposal_id"].startswith("psd2_cns_")


def test_create_consent_proposal_deterministic_id() -> None:
    """Same inputs = same proposal_id."""
    agent1 = _make_agent()
    agent2 = _make_agent()
    p1 = agent1.create_consent_proposal(_GB_IBAN, "allAccounts", _VALID_UNTIL, _OPS_EMAIL)
    p2 = agent2.create_consent_proposal(_GB_IBAN, "allAccounts", _VALID_UNTIL, _OPS_EMAIL)
    assert p1["proposal_id"] == p2["proposal_id"]


def test_create_consent_proposal_does_not_auto_create() -> None:
    """I-27: Proposal must NOT auto-create consent in store."""
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    agent.create_consent_proposal(_GB_IBAN, "allAccounts", _VALID_UNTIL, _OPS_EMAIL)

    # Proposal should NOT create a real consent
    assert len(consent_store.list_active()) == 0


# ── get_accounts ───────────────────────────────────────────────────────────


def test_get_accounts_after_real_consent() -> None:
    """Test get_accounts using a real consent (via client, not proposal)."""
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    # Create consent directly via client (simulating approved HITL proposal)
    consent = client.create_consent(_req())

    accounts = agent.get_accounts(consent.consent_id)
    assert len(accounts) >= 1


def test_get_accounts_unknown_consent_raises() -> None:
    agent = _make_agent()
    with pytest.raises(KeyError):
        agent.get_accounts("nonexistent")


# ── get_transactions ───────────────────────────────────────────────────────


def test_get_transactions_amount_decimal() -> None:
    """I-01: Returned amounts must be Decimal."""
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    consent = client.create_consent(_req())
    accounts = agent.get_accounts(consent.consent_id)
    txns = agent.get_transactions(consent.consent_id, accounts[0].account_id, _DATE_FROM, _DATE_TO)

    for txn in txns:
        assert isinstance(txn.amount, Decimal)


def test_get_transactions_appends_i24() -> None:
    """I-24: get_transactions must append to store."""
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    consent = client.create_consent(_req())
    accounts = agent.get_accounts(consent.consent_id)
    agent.get_transactions(consent.consent_id, accounts[0].account_id, _DATE_FROM, _DATE_TO)

    assert len(txn_store.list_by_account(accounts[0].account_id)) >= 1


# ── get_balances ───────────────────────────────────────────────────────────


def test_get_balances_decimal_amount() -> None:
    """I-01: Balance amount must be Decimal."""
    consent_store = InMemoryConsentStore()
    client = AdorsysClient(consent_store=consent_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    consent = client.create_consent(_req())
    accounts = agent.get_accounts(consent.consent_id)
    bal = agent.get_balances(consent.consent_id, accounts[0].account_id)

    assert isinstance(bal.balance_amount, Decimal)


# ── configure_auto_pull (I-27 HITL L4) ────────────────────────────────────


def test_configure_auto_pull_hitl_type() -> None:
    """I-27: configure_auto_pull must return HITLProposal."""
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    assert proposal["proposal_type"] == "HITL_REQUIRED"


def test_configure_auto_pull_l4_autonomy() -> None:
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    assert proposal["autonomy_level"] == "L4"


def test_configure_auto_pull_compliance_officer() -> None:
    """I-27: Pull config requires COMPLIANCE_OFFICER."""
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    assert proposal["requires_approval_from"] == "COMPLIANCE_OFFICER"


def test_configure_auto_pull_action_field() -> None:
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    assert proposal["action"] == "configure_auto_pull"


def test_configure_auto_pull_masks_iban() -> None:
    """No PII: IBAN must be masked."""
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    iban_in_data = proposal["data"]["iban"]
    assert iban_in_data.endswith("***")


def test_configure_auto_pull_has_proposal_id() -> None:
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "daily", _OPS_EMAIL)
    assert proposal["proposal_id"].startswith("psd2_pull_")


def test_configure_auto_pull_frequency_in_data() -> None:
    agent = _make_agent()
    proposal = agent.configure_auto_pull(_GB_IBAN, "weekly", _OPS_EMAIL)
    assert proposal["data"]["frequency"] == "weekly"


# ── get_active_consents ────────────────────────────────────────────────────


def test_get_active_consents_empty_initially() -> None:
    agent = _make_agent()
    assert agent.get_active_consents() == []


def test_get_active_consents_after_create() -> None:
    consent_store = InMemoryConsentStore()
    client = AdorsysClient(consent_store=consent_store)
    agent = PSD2Agent(client=client)
    agent._consent_store = consent_store

    client.create_consent(_req())

    active = agent.get_active_consents()
    assert len(active) == 1
