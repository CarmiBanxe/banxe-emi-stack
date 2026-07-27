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


# ══════════════════════════════════════════════════════════════════════════════
# IL-S4-WAVE2-01 — Wave 2 coverage (tests only; NO service code changed):
#   cbpii_consent / intl_scheduled / psd2_flow_handler / adorsys_client.
# All four are sandbox/stub (in-memory) — no live HTTP, nothing to mock out.
# ══════════════════════════════════════════════════════════════════════════════


# ── 12. open_banking.cbpii_consent.SandboxCbpiiProvider ──────────────────────


def test_cbpii_consent_lifecycle_and_idempotency() -> None:
    from services.open_banking.cbpii_consent import (
        EXISTING_CHECK_REF,
        CbpiiConsentStage,
        FundsConfirmationRef,
        SandboxCbpiiProvider,
        _default_consent_id,
    )

    provider = SandboxCbpiiProvider(id_generator=lambda: "CBPII-fixed-1")
    c = provider.create_consent(
        idempotency_key="idem-1", debtor_account_ref="INTERNAL", timestamp="2026-07-15T00:00:00Z"
    )
    assert c.stage is CbpiiConsentStage.AWAITING_AUTHORISATION
    assert c.consent_id == "CBPII-fixed-1"
    # idempotent by key: same key returns the same object (no new id minted)
    assert (
        provider.create_consent(
            idempotency_key="idem-1",
            debtor_account_ref="INTERNAL",
            timestamp="2026-07-15T00:00:00Z",
        )
        is c
    )
    assert provider.get_consent("CBPII-fixed-1") is c
    assert provider.get_consent("nope") is None
    ref = provider.funds_confirmation_ref("CBPII-fixed-1")
    assert isinstance(ref, FundsConfirmationRef)
    assert ref.delegates_to == EXISTING_CHECK_REF
    assert "INTERNAL" in provider.known_account_refs()
    assert _default_consent_id().startswith("CBPII-")


def test_cbpii_advance_transitions_and_fail_closed() -> None:
    from services.open_banking.cbpii_consent import CbpiiConsentStage, SandboxCbpiiProvider

    provider = SandboxCbpiiProvider(id_generator=lambda: "CBPII-adv")
    provider.create_consent(idempotency_key="k", debtor_account_ref="INTERNAL", timestamp="t")
    a = provider.advance(consent_id="CBPII-adv", to_stage=CbpiiConsentStage.AUTHORISED)
    assert a.stage is CbpiiConsentStage.AUTHORISED
    r = provider.advance(consent_id="CBPII-adv", to_stage=CbpiiConsentStage.REVOKED)
    assert r.stage is CbpiiConsentStage.REVOKED
    # REVOKED is terminal → illegal transition is fail-closed
    with pytest.raises(ValueError, match="illegal transition"):
        provider.advance(consent_id="CBPII-adv", to_stage=CbpiiConsentStage.AUTHORISED)
    with pytest.raises(KeyError):
        provider.advance(consent_id="ghost", to_stage=CbpiiConsentStage.AUTHORISED)


def test_cbpii_id_collision_is_fail_closed() -> None:
    from services.open_banking.cbpii_consent import SandboxCbpiiProvider

    # generator that always returns the same id → second create exhausts attempts
    provider = SandboxCbpiiProvider(id_generator=lambda: "DUP")
    provider.create_consent(idempotency_key="a", debtor_account_ref="INTERNAL", timestamp="t")
    with pytest.raises(RuntimeError, match="unique consent_id"):
        provider.create_consent(idempotency_key="b", debtor_account_ref="INTERNAL", timestamp="t")


# ── 13. open_banking.intl_scheduled.SandboxIntlScheduledProvider ─────────────

_INTL_KW = {
    "payment_intent_ref": "pi-1",
    "debtor_account_ref": "INTERNAL",
    "creditor_account_ref": "EXTERNAL",
    "creditor_iban": "DE89370400440532013000",
    "creditor_country": "DE",
    "currency": "GBP",
    "fx_indicator": False,
    "execution_date": "2026-08-01",
}


def test_intl_scheduled_lifecycle_and_minor_units() -> None:
    from services.open_banking.intl_scheduled import (
        IntlScheduledStage,
        SandboxIntlScheduledProvider,
        _default_intent_id,
    )

    provider = SandboxIntlScheduledProvider(id_generator=lambda: "INTL-1")
    intent = provider.create_consent(file_dedup_key="f1", amount=Decimal("12.34"), **_INTL_KW)
    assert intent.amount_minor == 1234  # Decimal (I-01) → minor units (I-05)
    assert intent.stage is IntlScheduledStage.CONSENT_AWAITING
    # idempotent by file_dedup_key (a different amount does not create a new intent)
    assert (
        provider.create_consent(file_dedup_key="f1", amount=Decimal("99.99"), **_INTL_KW) is intent
    )
    assert provider.get_intent("INTL-1") is intent
    assert provider.get_intent("none") is None
    assert "INTERNAL" in provider.known_account_refs()
    assert _default_intent_id().startswith("INTLSCHED-")


def test_intl_scheduled_advance_and_fail_closed() -> None:
    from services.open_banking.intl_scheduled import (
        IntlScheduledStage,
        SandboxIntlScheduledProvider,
    )

    provider = SandboxIntlScheduledProvider(id_generator=lambda: "INTL-adv")
    provider.create_consent(file_dedup_key="f", amount=Decimal("1.00"), **_INTL_KW)
    provider.advance(intent_id="INTL-adv", to_stage=IntlScheduledStage.CONSENT_AUTHORISED)
    provider.advance(intent_id="INTL-adv", to_stage=IntlScheduledStage.SCHEDULED)
    ex = provider.advance(intent_id="INTL-adv", to_stage=IntlScheduledStage.EXECUTED)
    assert ex.stage is IntlScheduledStage.EXECUTED
    with pytest.raises(ValueError, match="illegal transition"):
        provider.advance(intent_id="INTL-adv", to_stage=IntlScheduledStage.SCHEDULED)
    with pytest.raises(KeyError):
        provider.advance(intent_id="ghost", to_stage=IntlScheduledStage.SCHEDULED)


def test_intl_scheduled_id_collision_is_fail_closed() -> None:
    from services.open_banking.intl_scheduled import SandboxIntlScheduledProvider

    provider = SandboxIntlScheduledProvider(id_generator=lambda: "DUP")
    provider.create_consent(file_dedup_key="a", amount=Decimal("1.00"), **_INTL_KW)
    with pytest.raises(RuntimeError, match="unique intent_id"):
        provider.create_consent(file_dedup_key="b", amount=Decimal("1.00"), **_INTL_KW)


# ── 14. psd2_gateway.adorsys_client.AdorsysClient (stub — no live HTTP) ───────


def test_adorsys_client_full_read_flow() -> None:
    from services.psd2_gateway.adorsys_client import AdorsysClient
    from services.psd2_gateway.psd2_models import (
        AccountInfo,
        BalanceResponse,
        ConsentRequest,
        Transaction,
    )

    client = AdorsysClient(base_url="http://x:8889/")  # trailing slash exercises rstrip
    req = ConsentRequest(
        iban="GB29NWBK60161331926819", access_type="allAccounts", valid_until="2027-01-01"
    )
    consent = client.create_consent(req)
    assert consent.consent_id.startswith("cns_")
    assert consent.iban == req.iban
    accts = client.get_accounts(consent.consent_id)
    assert isinstance(accts[0], AccountInfo)
    acc_id = accts[0].account_id
    txns = client.get_transactions(consent.consent_id, acc_id, "2026-01-01", "2026-02-01")
    assert isinstance(txns[0], Transaction)
    assert txns[0].amount == Decimal("1500.00")
    bal = client.get_balances(consent.consent_id, acc_id)
    assert isinstance(bal, BalanceResponse)
    assert bal.balance_amount == Decimal("50000.00")


def test_adorsys_blocked_jurisdiction_and_unknown_consent() -> None:
    from services.psd2_gateway.adorsys_client import AdorsysClient
    from services.psd2_gateway.psd2_models import ConsentRequest

    client = AdorsysClient()
    # I-02: IBAN from a blocked jurisdiction (RU) is rejected
    with pytest.raises(ValueError, match="I-02"):
        client.create_consent(
            ConsentRequest(
                iban="RU0204452560040702810412345678901",
                access_type="allAccounts",
                valid_until="2027-01-01",
            )
        )
    # unknown consent is fail-closed (KeyError) on every read path
    with pytest.raises(KeyError):
        client.get_accounts("nope")
    with pytest.raises(KeyError):
        client.get_transactions("nope", "acc", "2026-01-01", "2026-02-01")
    with pytest.raises(KeyError):
        client.get_balances("nope", "acc")


def test_adorsys_pisp_initiation_not_enabled() -> None:
    from services.psd2_gateway.adorsys_client import AdorsysClient

    with pytest.raises(RuntimeError, match="BT-007"):
        AdorsysClient().initiate_payment_via_psd2()


# ── 15. consent_management.psd2_flow_handler.PSD2FlowHandler ─────────────────


def test_psd2_flow_aisp_initiate_and_activate() -> None:
    from services.consent_management.models import ConsentScope, ConsentStatus
    from services.consent_management.psd2_flow_handler import (
        PSD2FlowHandler,
        _make_consent_id,
        _make_event_id,
    )

    handler = PSD2FlowHandler()
    # unregistered TPP → fail-closed ValueError (PSD2 Art.65)
    with pytest.raises(ValueError, match="not REGISTERED"):
        handler.initiate_aisp_flow("cust-1", "tpp_unknown", [ConsentScope.ACCOUNTS], "https://cb")
    # seeded REGISTERED TPP → PENDING consent
    grant = handler.initiate_aisp_flow(
        "cust-1", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://cb", ttl_days=30
    )
    assert grant.status is ConsentStatus.PENDING
    active = handler.complete_aisp_flow(grant.consent_id, customer_approved=True)
    assert active.status is ConsentStatus.ACTIVE
    assert _make_consent_id("aisp", "c", "t", "ts").startswith("cns_")
    assert _make_event_id("cns", "X", "ts").startswith("evt_")


def test_psd2_flow_complete_reject_and_not_found() -> None:
    from services.consent_management.models import ConsentScope, ConsentStatus
    from services.consent_management.psd2_flow_handler import PSD2FlowHandler

    handler = PSD2FlowHandler()
    with pytest.raises(ValueError, match="not found"):
        handler.complete_aisp_flow("ghost", customer_approved=True)
    grant = handler.initiate_aisp_flow(
        "cust-2", "tpp_truelayer", [ConsentScope.BALANCES], "https://cb"
    )
    revoked = handler.complete_aisp_flow(grant.consent_id, customer_approved=False)
    assert revoked.status is ConsentStatus.REVOKED


def test_psd2_flow_pisp_is_always_hitl() -> None:
    from services.consent_management.psd2_flow_handler import PSD2FlowHandler

    proposal = PSD2FlowHandler().initiate_pisp_payment("cns-x", Decimal("42.00"), "payee-1")
    assert proposal.action == "INITIATE_PISP_PAYMENT"
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"
    assert proposal.autonomy_level == "L4"  # I-27


def test_psd2_flow_cbpii_edd_threshold_and_funds_confirmed() -> None:
    from services.consent_management.models import ConsentScope
    from services.consent_management.psd2_flow_handler import EDD_THRESHOLD, PSD2FlowHandler

    handler = PSD2FlowHandler()
    # amount at/above EDD threshold → ValueError (I-04)
    with pytest.raises(ValueError, match="EDD"):
        handler.handle_cbpii_check("any", EDD_THRESHOLD)
    # ACTIVE consent + amount below threshold → funds confirmed True
    grant = handler.initiate_aisp_flow(
        "cust-3", "tpp_plaid_uk", [ConsentScope.ACCOUNTS], "https://cb"
    )
    handler.complete_aisp_flow(grant.consent_id, customer_approved=True)
    assert handler.handle_cbpii_check(grant.consent_id, Decimal("50")) is True
