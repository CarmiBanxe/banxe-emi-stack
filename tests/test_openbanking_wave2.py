"""
tests/test_openbanking_wave2.py — Sprint 4 Track B Wave 2 coverage gap-closer.
IL-OBK-01 | banxe-emi-stack

Targets uncovered lines in services/open_banking/ + consent_management/:
  - aspsp_adapter.py L10-180 (0% → 100%): BerlinGroup + UKOBIE adapters
  - token_manager.py L61-130 (52% → 100%): get_token, revoke, is_valid, cache
  - sca_orchestrator.py L64,77-78,115-154 (71% → 100%): complete_sca, get_challenge
  - aisp_service.py L64, pisp_service.py L129: edge paths
  - consent_manager.py L154: is_valid boundary
  - psd2_flow_handler.py L243: CBPII expired/inactive consent

PSD2 RTS Art.4 (SCA), Art.10 (consent 90-day), Art.65-67 (AISP/PISP/CBPII).
Berlin Group NextGenPSD2 3.1. UK OBIE 3.1. PSR 2017.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.open_banking.aspsp_adapter import (
    BerlinGroupAdapter,
    UKOBIEAdapter,
)
from services.open_banking.consent_manager import ConsentManager
from services.open_banking.models import (
    AccountAccessType,
    Consent,
    ConsentStatus,
    ConsentType,
    FlowType,
    InMemoryAccountData,
    InMemoryASPSPRegistry,
    InMemoryConsentStore,
    InMemoryOBAuditTrail,
    InMemoryPaymentGateway,
    PaymentInitiation,
    PaymentStatus,
)
from services.open_banking.pisp_service import PISPService
from services.open_banking.sca_orchestrator import SCAOrchestrator
from services.open_banking.token_manager import TokenManager

# ── Helpers ────────────────────────────────────────────────────────────────────

_NOW = datetime.now(UTC)


def _make_payment(**overrides: object) -> PaymentInitiation:
    defaults: dict = {
        "id": "pay-001",
        "consent_id": "cns-001",
        "entity_id": "ent-001",
        "aspsp_id": "barclays-uk",
        "amount": Decimal("100.00"),
        "currency": "GBP",
        "creditor_iban": "GB29NWBK60161331926819",
        "creditor_name": "Alice",
        "reference": "Invoice 42",
        "status": PaymentStatus.PENDING,
        "created_at": _NOW,
        "end_to_end_id": "e2e-001",
    }
    defaults.update(overrides)
    return PaymentInitiation(**defaults)


def _registry_with_aspsp() -> InMemoryASPSPRegistry:
    """Pre-seeded with barclays-uk (OBIE), hsbc-uk (OBIE), bnp-fr (Berlin)."""
    return InMemoryASPSPRegistry()


async def _seed_consent(
    store: InMemoryConsentStore,
    consent_id: str = "cns-001",
    status: ConsentStatus = ConsentStatus.AUTHORISED,
    consent_type: ConsentType = ConsentType.AISP,
    permissions: list[AccountAccessType] | None = None,
) -> Consent:
    consent = Consent(
        id=consent_id,
        type=consent_type,
        aspsp_id="barclays-uk",
        entity_id="ent-001",
        permissions=permissions or [AccountAccessType.ACCOUNTS],
        status=status,
        created_at=_NOW,
        expires_at=_NOW + timedelta(days=90),
    )
    await store.save(consent)
    return consent


# ── 1. BerlinGroupAdapter consent request ─────────────────────────────────────


def test_berlin_group_consent_request() -> None:
    adapter = BerlinGroupAdapter()
    perms = [
        AccountAccessType.ACCOUNTS,
        AccountAccessType.BALANCES,
        AccountAccessType.TRANSACTIONS,
    ]
    result = adapter.build_consent_request(ConsentType.AISP, perms)

    assert "access" in result
    assert "accounts" in result["access"]
    assert "balances" in result["access"]
    assert "transactions" in result["access"]
    assert result["frequencyPerDay"] == 4
    assert result["recurringIndicator"] is True


# ── 2. BerlinGroupAdapter payment request ─────────────────────────────────────


def test_berlin_group_payment_request() -> None:
    adapter = BerlinGroupAdapter()
    payment = _make_payment(debtor_iban="DE89370400440532013000")
    result = adapter.build_payment_request(payment)

    assert result["instructedAmount"]["currency"] == "GBP"
    assert result["instructedAmount"]["amount"] == "100.00"
    assert result["creditorName"] == "Alice"
    assert "debtorAccount" in result

    # Without debtor
    payment_no_debtor = _make_payment(debtor_iban=None)
    result2 = adapter.build_payment_request(payment_no_debtor)
    assert "debtorAccount" not in result2

    # parse_payment_response
    assert adapter.parse_payment_response({"paymentId": "pid-1"}) == "pid-1"
    with pytest.raises(ValueError, match="No paymentId"):
        adapter.parse_payment_response({})


# ── 3. UKOBIEAdapter consent request ──────────────────────────────────────────


def test_obie_consent_request() -> None:
    adapter = UKOBIEAdapter()
    perms = [AccountAccessType.ACCOUNTS, AccountAccessType.BENEFICIARIES]
    result = adapter.build_consent_request(ConsentType.AISP, perms)

    assert "Data" in result
    obie_perms = result["Data"]["Permissions"]
    assert "ReadAccountsBasic" in obie_perms
    assert "ReadBeneficiariesBasic" in obie_perms


# ── 4. UKOBIEAdapter payment request ──────────────────────────────────────────


def test_obie_payment_request() -> None:
    adapter = UKOBIEAdapter()
    payment = _make_payment(debtor_iban="GB29NWBK60161331926819")
    result = adapter.build_payment_request(payment)

    data = result["Data"]
    assert data["ConsentId"] == "cns-001"
    assert data["Initiation"]["InstructedAmount"]["Amount"] == "100.00"
    assert "DebtorAccount" in data["Initiation"]

    # Without debtor
    payment_no_debtor = _make_payment(debtor_iban=None)
    result2 = adapter.build_payment_request(payment_no_debtor)
    assert "DebtorAccount" not in result2["Data"]["Initiation"]

    # parse_payment_response
    resp = {"Data": {"DomesticPaymentId": "dpid-1"}}
    assert adapter.parse_payment_response(resp) == "dpid-1"
    with pytest.raises(ValueError, match="No DomesticPaymentId"):
        adapter.parse_payment_response({"Data": {}})


# ── 5. TokenManager get_token + cache ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_manager_get_token_and_cache() -> None:
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    tm = TokenManager(registry=registry, audit=audit)

    token1 = await tm.get_token("barclays-uk", "accounts")
    assert token1.aspsp_id == "barclays-uk"
    assert token1.scope == "accounts"
    assert token1.expires_at > _NOW

    # Cache hit — same object returned
    token2 = await tm.get_token("barclays-uk", "accounts")
    assert token2.token == token1.token

    # Unknown ASPSP raises
    with pytest.raises(ValueError, match="ASPSP not found"):
        await tm.get_token("unknown-bank", "accounts")


# ── 6. TokenManager revoke + is_valid ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_token_manager_revoke_and_validity() -> None:
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    tm = TokenManager(registry=registry, audit=audit)

    token = await tm.get_token("barclays-uk", "accounts")
    assert await tm.is_valid(token) is True

    removed = await tm.revoke_token("barclays-uk", "accounts", actor="admin")
    assert removed is True

    # Revoking again returns False (no token in cache)
    removed2 = await tm.revoke_token("barclays-uk", "accounts", actor="admin")
    assert removed2 is False

    # Cache key helper
    key = tm._make_cache_key("bank-a", "payments", "cns-x")
    assert key == "bank-a:payments:cns-x"
    key_global = tm._make_cache_key("bank-a", "payments", None)
    assert key_global == "bank-a:payments:global"


# ── 7. SCAOrchestrator complete_sca + get_challenge ───────────────────────────


@pytest.mark.asyncio
async def test_sca_complete_and_get_challenge() -> None:
    store = InMemoryConsentStore()
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    cm = ConsentManager(store=store, registry=registry, audit=audit)
    sca = SCAOrchestrator(consent_manager=cm, audit=audit)

    consent = await cm.create_consent(
        entity_id="ent-001",
        aspsp_id="barclays-uk",
        consent_type=ConsentType.AISP,
        permissions=[AccountAccessType.ACCOUNTS],
        actor="user-1",
    )

    # Initiate DECOUPLED flow (covers L77-78)
    challenge = await sca.initiate_sca(
        consent.id,
        FlowType.DECOUPLED,
        actor="user-1",
    )
    assert challenge.otp_hint is not None
    assert challenge.redirect_url is None

    # get_challenge (covers L154)
    fetched = await sca.get_challenge(challenge.id)
    assert fetched is not None
    assert fetched.id == challenge.id

    # get_challenge for unknown returns None
    assert await sca.get_challenge("nonexistent") is None

    # complete_sca (covers L115-150)
    result_consent = await sca.complete_sca(
        challenge.id,
        auth_code="123456",
        actor="user-1",
    )
    assert result_consent.status == ConsentStatus.AUTHORISED


# ── 8. SCAOrchestrator expired + already completed guards ────────────────────


@pytest.mark.asyncio
async def test_sca_complete_expired_and_already_done() -> None:
    store = InMemoryConsentStore()
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    cm = ConsentManager(store=store, registry=registry, audit=audit)
    sca = SCAOrchestrator(consent_manager=cm, audit=audit)

    consent = await cm.create_consent(
        entity_id="ent-001",
        aspsp_id="barclays-uk",
        consent_type=ConsentType.AISP,
        permissions=[AccountAccessType.ACCOUNTS],
        actor="user-1",
    )

    # Not-found challenge
    with pytest.raises(ValueError, match="SCA challenge not found"):
        await sca.complete_sca("bad-id", "code", "user-1")

    # Not-found consent for initiate_sca (covers L64)
    with pytest.raises(ValueError, match="Consent not found"):
        await sca.initiate_sca("nonexistent", FlowType.REDIRECT, "user-1")

    # Create and complete, then try again (already completed)
    challenge = await sca.initiate_sca(
        consent.id,
        FlowType.REDIRECT,
        actor="user-1",
    )
    assert challenge.redirect_url is not None
    await sca.complete_sca(challenge.id, "code-1", "user-1")

    with pytest.raises(ValueError, match="already completed"):
        await sca.complete_sca(challenge.id, "code-2", "user-1")

    # Expired challenge
    challenge2 = await sca.initiate_sca(
        consent.id,
        FlowType.EMBEDDED,
        actor="user-1",
    )
    # Force expire by replacing with past expires_at
    from services.open_banking.sca_orchestrator import SCAChallenge

    sca._challenges[challenge2.id] = SCAChallenge(
        id=challenge2.id,
        consent_id=challenge2.consent_id,
        flow_type=challenge2.flow_type,
        redirect_url=challenge2.redirect_url,
        otp_hint=challenge2.otp_hint,
        expires_at=_NOW - timedelta(minutes=1),
    )
    with pytest.raises(ValueError, match="expired"):
        await sca.complete_sca(challenge2.id, "code-3", "user-1")


# ── 9. AISP permission error + PISP status fallback ──────────────────────────


@pytest.mark.asyncio
async def test_aisp_permission_error_pisp_status_fallback() -> None:
    from services.open_banking.aisp_service import AISPService

    store = InMemoryConsentStore()
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    account_data = InMemoryAccountData()
    cm = ConsentManager(store=store, registry=registry, audit=audit)
    aisp = AISPService(
        consent_manager=cm,
        account_data=account_data,
        audit=audit,
    )

    # Create consent with ACCOUNTS only
    consent = await cm.create_consent(
        entity_id="ent-001",
        aspsp_id="barclays-uk",
        consent_type=ConsentType.AISP,
        permissions=[AccountAccessType.ACCOUNTS],
        actor="user-1",
    )
    await cm.authorise_consent(consent.id, "auth-code", "user-1")

    # Request BALANCES permission → error (L64)
    with pytest.raises(ValueError, match="does not include permission"):
        await aisp.get_balance(consent.id, "acc-001", "user-1")

    # PISP: get_payment_status without aspsp_payment_id (L129)
    gateway = InMemoryPaymentGateway()
    pisp = PISPService(consent_manager=cm, gateway=gateway, audit=audit)
    payment = _make_payment(aspsp_payment_id=None, status=PaymentStatus.PENDING)
    status = await pisp.get_payment_status(payment)
    assert status == PaymentStatus.PENDING


# ── 10. ConsentManager.is_valid boundary + PSD2 CBPII check ─────────────────


@pytest.mark.asyncio
async def test_consent_edge_and_cbpii_check() -> None:
    # ConsentManager.is_valid (L154) — expired consent
    store = InMemoryConsentStore()
    registry = _registry_with_aspsp()
    audit = InMemoryOBAuditTrail()
    cm = ConsentManager(store=store, registry=registry, audit=audit)

    # Non-existent consent
    assert await cm.is_valid("nonexistent") is False

    consent = await cm.create_consent(
        entity_id="ent-001",
        aspsp_id="barclays-uk",
        consent_type=ConsentType.AISP,
        permissions=[AccountAccessType.ACCOUNTS],
        actor="user-1",
    )
    # Not yet authorised → False
    assert await cm.is_valid(consent.id) is False

    # PSD2FlowHandler CBPII: expired/inactive consent (L243)
    from services.consent_management.psd2_flow_handler import PSD2FlowHandler

    handler = PSD2FlowHandler()
    # No consent → False
    assert handler.handle_cbpii_check("no-such-consent", Decimal("50")) is False

    # Consent exists but EXPIRED status → False (L243)
    from services.consent_management.models import ConsentGrant, ConsentScope
    from services.consent_management.models import ConsentStatus as CmConsentStatus
    from services.consent_management.models import ConsentType as CmConsentType

    expired_consent = ConsentGrant(
        consent_id="cns-cbpii-001",
        customer_id="cust-001",
        tpp_id="tpp-001",
        consent_type=CmConsentType.CBPII,
        scopes=[ConsentScope.PAYMENTS],
        status=CmConsentStatus.ACTIVE,
        granted_at=(_NOW - timedelta(days=100)).isoformat(),
        expires_at=(_NOW - timedelta(days=1)).isoformat(),
        redirect_uri="https://tpp.example.com/callback",
    )
    handler._store.save(expired_consent)
    assert handler.handle_cbpii_check("cns-cbpii-001", Decimal("50")) is False


# ── 11. ASPSPAdapter unified delegator (L142-180) ────────────────────────────


@pytest.mark.asyncio
async def test_aspsp_adapter_unified_delegation() -> None:
    """Cover ASPSPAdapter async methods that delegate to Berlin/OBIE."""
    from services.open_banking.aspsp_adapter import ASPSPAdapter

    registry = _registry_with_aspsp()
    adapter = ASPSPAdapter(registry=registry)

    # OBIE consent (barclays-uk is UK_OBIE)
    obie_consent = await adapter.build_consent_request(
        "barclays-uk",
        ConsentType.AISP,
        [AccountAccessType.ACCOUNTS],
    )
    assert "Data" in obie_consent

    # Berlin Group consent (bnp-fr is BERLIN_GROUP)
    bg_consent = await adapter.build_consent_request(
        "bnp-fr",
        ConsentType.AISP,
        [AccountAccessType.ACCOUNTS],
    )
    assert "access" in bg_consent

    # OBIE payment
    payment_obie = _make_payment(aspsp_id="barclays-uk")
    obie_pay = await adapter.build_payment_request(payment_obie)
    assert "Data" in obie_pay

    # Berlin Group payment
    payment_bg = _make_payment(aspsp_id="bnp-fr")
    bg_pay = await adapter.build_payment_request(payment_bg)
    assert "instructedAmount" in bg_pay

    # parse_payment_response — OBIE
    pid = await adapter.parse_payment_response(
        "barclays-uk",
        {"Data": {"DomesticPaymentId": "dp-1"}},
    )
    assert pid == "dp-1"

    # parse_payment_response — Berlin Group
    pid2 = await adapter.parse_payment_response(
        "bnp-fr",
        {"paymentId": "bg-1"},
    )
    assert pid2 == "bg-1"

    # Unknown ASPSP raises
    with pytest.raises(ValueError, match="ASPSP not found"):
        await adapter.build_consent_request(
            "unknown",
            ConsentType.AISP,
            [AccountAccessType.ACCOUNTS],
        )
    with pytest.raises(ValueError, match="ASPSP not found"):
        await adapter.build_payment_request(_make_payment(aspsp_id="unknown"))
    with pytest.raises(ValueError, match="ASPSP not found"):
        await adapter.parse_payment_response("unknown", {})
