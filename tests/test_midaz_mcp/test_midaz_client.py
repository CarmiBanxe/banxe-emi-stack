"""Tests for Midaz MCP Integration (IL-MCP-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.midaz_mcp.midaz_client import (
    BLOCKED_JURISDICTIONS,
    EDD_THRESHOLD,
    MidazClient,
)
from services.midaz_mcp.midaz_models import TransactionEntry


@pytest.mark.asyncio
class TestMidazClientOrganization:
    async def test_create_org_returns_organization(self):
        client = MidazClient()
        org = await client.create_organization("Banxe", "Banxe Ltd", "GB")
        assert org.name == "Banxe"
        assert org.country == "GB"

    async def test_create_org_blocked_ru(self):
        client = MidazClient()
        with pytest.raises(ValueError, match="I-02"):
            await client.create_organization("Bad Corp", "Bad Corp LLC", "RU")

    async def test_create_org_blocked_ir(self):
        client = MidazClient()
        with pytest.raises(ValueError, match="I-02"):
            await client.create_organization("Bad Corp", "Bad Corp LLC", "IR")

    async def test_create_org_blocked_kp(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "KP")

    async def test_create_org_blocked_by(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "BY")

    async def test_create_org_blocked_cu(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "CU")

    async def test_create_org_blocked_mm(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "MM")

    async def test_create_org_blocked_sy(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "SY")

    async def test_create_org_blocked_ve(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "VE")

    async def test_create_org_blocked_af(self):
        client = MidazClient()
        with pytest.raises(ValueError):
            await client.create_organization("Corp", "Corp", "AF")

    async def test_create_org_allowed_gb(self):
        client = MidazClient()
        org = await client.create_organization("UK Corp", "UK Corp Ltd", "GB")
        assert org.org_id is not None

    async def test_create_org_allowed_de(self):
        client = MidazClient()
        org = await client.create_organization("DE Corp", "DE Corp GmbH", "DE")
        assert org.country == "DE"

    async def test_create_org_allowed_fr(self):
        client = MidazClient()
        org = await client.create_organization("FR Corp", "FR Corp SA", "FR")
        assert org.country == "FR"

    async def test_blocked_jurisdictions_set_correct(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "IR" in BLOCKED_JURISDICTIONS
        assert "KP" in BLOCKED_JURISDICTIONS
        assert "BY" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS

    async def test_create_org_stores_legal_name(self):
        client = MidazClient()
        org = await client.create_organization("Banxe", "Banxe Financial Services Ltd", "GB")
        assert org.legal_name == "Banxe Financial Services Ltd"


@pytest.mark.asyncio
class TestMidazClientLedger:
    async def test_create_ledger_returns_ledger(self):
        client = MidazClient()
        ledger = await client.create_ledger("org_001", "Main Ledger")
        assert ledger.ledger_id is not None
        assert ledger.org_id == "org_001"

    async def test_create_ledger_name_stored(self):
        client = MidazClient()
        ledger = await client.create_ledger("org_001", "Safeguarding Ledger")
        assert ledger.name == "Safeguarding Ledger"

    async def test_create_multiple_ledgers(self):
        client = MidazClient()
        ledger1 = await client.create_ledger("org_001", "Ledger A")
        ledger2 = await client.create_ledger("org_001", "Ledger B")
        assert ledger1.ledger_id != ledger2.ledger_id


@pytest.mark.asyncio
class TestMidazClientAccount:
    async def test_create_account_returns_account(self):
        client = MidazClient()
        account = await client.create_account("ldg_001", "ast_001", "Savings", "savings")
        assert account.account_id is not None
        assert account.name == "Savings"

    async def test_create_account_type_stored(self):
        client = MidazClient()
        account = await client.create_account("ldg_001", "ast_001", "Deposit", "deposit")
        assert account.account_type == "deposit"

    async def test_list_accounts_by_ledger(self):
        client = MidazClient()
        await client.create_account("ldg_001", "ast_001", "Account A", "deposit")
        await client.create_account("ldg_001", "ast_001", "Account B", "deposit")
        accounts = await client.list_accounts("ldg_001")
        assert len(accounts) >= 1

    async def test_list_accounts_empty_ledger(self):
        client = MidazClient()
        accounts = await client.list_accounts("ldg_999")
        assert accounts == []


@pytest.mark.asyncio
class TestMidazClientTransaction:
    async def test_create_transaction_below_edd_threshold(self):
        client = MidazClient()
        entries = [
            TransactionEntry(account_id="acc_001", amount="500.00", direction="DEBIT"),
            TransactionEntry(account_id="acc_002", amount="500.00", direction="CREDIT"),
        ]
        tx = await client.create_transaction("ldg_001", entries)
        assert tx.transaction_id is not None
        assert tx.status == "POSTED"

    async def test_transaction_log_append_only(self):
        """I-24: transaction_log grows."""
        client = MidazClient()
        entries = [TransactionEntry(account_id="acc_001", amount="100.00", direction="DEBIT")]
        await client.create_transaction("ldg_001", entries)
        await client.create_transaction("ldg_001", entries)
        assert len(client.transaction_log) == 2

    async def test_transaction_log_not_empty_after_tx(self):
        client = MidazClient()
        entries = [TransactionEntry(account_id="acc_001", amount="200.00", direction="DEBIT")]
        await client.create_transaction("ldg_001", entries)
        assert len(client.transaction_log) >= 1

    async def test_transaction_entry_amount_is_decimal_string(self):
        entry = TransactionEntry(account_id="acc_001", amount="1000.00", direction="DEBIT")
        assert isinstance(entry.amount, str)
        d = Decimal(entry.amount)
        assert isinstance(d, Decimal)

    async def test_transaction_entry_rejects_negative(self):
        with pytest.raises(ValueError):
            TransactionEntry(account_id="acc_001", amount="-100.00", direction="DEBIT")

    async def test_transaction_entry_rejects_invalid_direction(self):
        with pytest.raises(ValueError):
            TransactionEntry(account_id="acc_001", amount="100.00", direction="INVALID")

    async def test_edd_threshold_is_decimal(self):
        assert isinstance(EDD_THRESHOLD, Decimal)
        assert Decimal("10000.00") == EDD_THRESHOLD

    async def test_get_balances_returns_list(self):
        client = MidazClient()
        balances = await client.get_balances("acc_001")
        assert isinstance(balances, list)

    async def test_balance_amount_is_string(self):
        client = MidazClient()
        balances = await client.get_balances("acc_001")
        for b in balances:
            assert isinstance(b.amount, str)
            Decimal(b.amount)

    async def test_transaction_log_has_ledger_id(self):
        client = MidazClient()
        entries = [TransactionEntry(account_id="acc_001", amount="100.00", direction="DEBIT")]
        await client.create_transaction("ldg_test", entries)
        log = client.transaction_log
        assert log[0]["ledger_id"] == "ldg_test"

    async def test_transaction_log_has_total_debit(self):
        client = MidazClient()
        entries = [
            TransactionEntry(account_id="acc_001", amount="250.00", direction="DEBIT"),
            TransactionEntry(account_id="acc_002", amount="250.00", direction="DEBIT"),
        ]
        await client.create_transaction("ldg_001", entries)
        log = client.transaction_log
        assert log[0]["total_debit"] == "500.00"


@pytest.mark.asyncio
class TestMidazAgent:
    async def test_small_transaction_posted_directly(self):
        from services.midaz_mcp.midaz_agent import MidazAgent

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="500.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        from services.midaz_mcp.midaz_models import Transaction

        assert isinstance(result, Transaction)

    async def test_large_transaction_returns_hitl_proposal(self):
        """I-27: >= £10k returns HITLProposal."""
        from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="10000.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, MidazHITLProposal)

    async def test_hitl_proposal_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="50000.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, MidazHITLProposal)
        assert result.approved is False

    async def test_hitl_proposal_requires_compliance_officer(self):
        from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="10001.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, MidazHITLProposal)
        assert result.requires_approval_from == "COMPLIANCE_OFFICER"

    async def test_edd_boundary_below_no_hitl(self):
        """£9,999.99 should NOT trigger HITL."""
        from services.midaz_mcp.midaz_agent import MidazAgent
        from services.midaz_mcp.midaz_models import Transaction

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="9999.99", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, Transaction)

    async def test_edd_boundary_at_threshold_triggers_hitl(self):
        """Exactly £10,000 triggers HITL."""
        from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="10000.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, MidazHITLProposal)

    async def test_proposals_appended(self):
        from services.midaz_mcp.midaz_agent import MidazAgent

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="15000.00", direction="DEBIT")]
        await agent.submit_transaction("ldg_001", entries)
        await agent.submit_transaction("ldg_001", entries)
        assert len(agent.proposals) == 2

    async def test_credit_entries_do_not_count_for_edd(self):
        """Only DEBIT entries count toward EDD threshold."""
        from services.midaz_mcp.midaz_agent import MidazAgent
        from services.midaz_mcp.midaz_models import Transaction

        agent = MidazAgent()
        entries = [
            TransactionEntry(account_id="acc_001", amount="20000.00", direction="CREDIT"),
            TransactionEntry(account_id="acc_002", amount="100.00", direction="DEBIT"),
        ]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, Transaction)

    async def test_hitl_proposal_has_proposed_at(self):
        from services.midaz_mcp.midaz_agent import MidazAgent, MidazHITLProposal

        agent = MidazAgent()
        entries = [TransactionEntry(account_id="acc_001", amount="10000.00", direction="DEBIT")]
        result = await agent.submit_transaction("ldg_001", entries)
        assert isinstance(result, MidazHITLProposal)
        assert result.proposed_at is not None
        assert len(result.proposed_at) > 0

    async def test_midaz_client_asset_creation(self):
        client = MidazClient()
        asset = await client.create_asset("ldg_001", "GBP", 2)
        assert asset.asset_id is not None
        assert asset.code == "GBP"
        assert asset.scale == 2
