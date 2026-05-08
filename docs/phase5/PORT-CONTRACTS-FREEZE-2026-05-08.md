# Port Contracts Freeze — Phase 5 Tranche 2
# Date: 2026-05-08 | Branch: feat/phase5-tranche-2-ports-freeze-2026-05-08
# Canon: ADR-015 + ADR-025 §15-16 + ADR-029
#
# FROZEN ports: signature changes require a new ADR + minor version bump.
# Any breaking change to a frozen port must be reviewed and merged separately.

## Frozen Status Legend

| Status   | Meaning                                                                    |
|----------|----------------------------------------------------------------------------|
| FROZEN   | Signature locked; has ≥1 production-track legacy adapter and test coverage |
| ACTIVE   | Implementation in progress (current sprint)                                |
| STUB     | Port defined; adapter is InMemory/stub only; no legacy counterpart yet     |

---

## 1. Payment Domain

### PaymentRailPort (`services/payment/payment_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `submit_payment` | `(self, intent: PaymentIntent) -> PaymentResult` |
| `get_payment_status` | `(self, provider_payment_id: str) -> PaymentResult` |
| `health` | `(self) -> bool` |

Implementing adapters:

| Adapter | File | Wave |
|---------|------|------|
| `LegacyTransactionsAdapter` | `services/payment/legacy/legacy_transactions_adapter.py` | C |
| `LegacyAbsPaymentAdapter` | `services/payment/legacy/legacy_abs_payment_adapter.py` | C |
| `LegacySepaAdapter` | `services/payment/legacy/legacy_sepa_adapter.py` | C |

### PaymentGatewayPort (`services/payment/payment_gateway_port.py`) — **STUB**

| Method | Signature |
|--------|-----------|
| `authorize` | `(self, request: GatewayRequest) -> GatewayResponse` |
| `capture` | `(self, gateway_reference: str, amount: Decimal) -> GatewayResponse` |
| `refund` | `(self, gateway_reference: str, amount: Decimal) -> GatewayResponse` |
| `get_status` | `(self, gateway_reference: str) -> GatewayResponse` |

Implementing adapters: `InMemoryPaymentGateway` (stub only)

---

## 2. KYC / Compliance Domain

### KYCWorkflowPort (`services/kyc/kyc_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `create_workflow` | `(self, request: KYCWorkflowRequest) -> KYCWorkflowResult` |
| `get_workflow` | `(self, workflow_id: str) -> KYCWorkflowResult \| None` |
| `submit_documents` | `(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult` |
| `approve_edd` | `(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult` |
| `reject_workflow` | `(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult` |
| `health` | `(self) -> bool` |

Implementing adapters:

| Adapter | File | Wave |
|---------|------|------|
| `LegacySumSubAdapter` | `services/compliance/legacy/legacy_sumsub_adapter.py` | D |
| `LegacyBinanceKYCAdapter` | `services/compliance/legacy/legacy_binancekyc_adapter.py` | D |

---

## 3. Auth Domain

### TokenManagerPort (`services/auth/token_manager_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `issue_access_token` | `(self, customer_id: str) -> tuple[str, datetime]` |
| `issue_refresh_token` | `(self, customer_id: str) -> tuple[str, datetime]` |
| `validate_access_token` | `(self, token: str) -> dict` |
| `validate_refresh_token` | `(self, token: str) -> dict` |
| `is_inactive` | `(self, last_activity: datetime) -> bool` |
| `rotate` | `(self, refresh_token: str) -> tuple[str, str, datetime, datetime]` |

Implementing adapters: `LegacyJwtStrategyAdapter` (`services/auth/legacy/jwt_strategy.py`, Wave A)

### TwoFactorPort (`services/auth/two_factor_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `setup_totp` | `(self, customer_id: str, account_name: str \| None = None) -> TOTPSetup` |
| `confirm_totp` | `(self, customer_id: str, otp: str) -> bool` |
| `is_enabled` | `(self, customer_id: str) -> bool` |
| `verify_totp` | `(self, customer_id: str, otp: str) -> VerifyResult` |
| `verify_backup_code` | `(self, customer_id: str, code: str) -> VerifyResult` |
| `revoke_totp` | `(self, customer_id: str) -> None` |
| `backup_codes_remaining` | `(self, customer_id: str) -> int` |

Implementing adapters: `LegacyTotpAdapter` (`services/auth/legacy/legacy_totp_adapter.py`, Wave B)

### SCAServicePort (`services/auth/sca_service_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `create_challenge` | `(self, ...) -> SCAChallenge` |
| `verify` | `(self, ...) -> bool` |
| `resend_challenge` | `(self, challenge_id: str) -> SCAChallenge` |

Implementing adapters: `LegacyScaAdapter` (`services/auth/legacy/legacy_sca_adapter.py`, Wave B)

### OTPDeliveryPort (`services/auth/otp_delivery_port.py`) — **ACTIVE**

| Method | Signature |
|--------|-----------|
| `generate_otp` | `(self, *, length: int = 6, alphabet: str = "digits") -> str` |
| `send_otp` | `(self, ...) -> ...` |
| `verify_otp` | `(self, ...) -> ...` |
| `can_resend` | `(self, ...) -> ...` |

Implementing adapters: `LegacyOTPAdapter` (`services/auth/legacy/legacy_otp_adapter.py`, Wave B — in progress)

### SCATokenIssuerPort (`services/auth/sca_token_issuer_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `issue` | `(self, challenge: SCAChallenge) -> str` |

---

## 4. Ledger / Crypto Domain

### LedgerPort (`services/ledger/ledger_port.py`) — **STUB**

| Method | Signature |
|--------|-----------|
| `create_account` | `(self, account: Account) -> Account` |
| `get_account` | `(self, account_id: str) -> Account \| None` |
| `post_journal_entry` | `(self, entry: JournalEntry) -> JournalEntry` |
| `get_journal_entry` | `(self, entry_id: str) -> JournalEntry \| None` |
| `get_account_balance` | `(self, account_id: str) -> Decimal` |

Implementing adapters: none (Midaz REST adapter Wave E+)

### CryptoLedgerPort (`services/ledger/crypto_ledger_port.py`) — **FROZEN**

| Method | Signature |
|--------|-----------|
| `get_balance` | `(self, ...) -> Decimal` |
| `create_wallet_address` | `(self, ...) -> str` |
| `create_tx` | `(self, ...) -> ...` |
| `get_fee_estimate` | `(self, ...) -> Decimal` |
| `health` | `(self) -> bool` |
| `broadcast_tx` | `(self, ...) -> ...` |
| `get_block` | `(self, ...) -> ...` |
| `estimate_fee` | `(self, ...) -> Decimal` |

Implementing adapters:

| Adapter | File | Wave |
|---------|------|------|
| `LegacyCryptoWalletAdapter` | `services/ledger/legacy/legacy_crypto_wallet_adapter.py` | E |
| `LegacyCryptoProcessingAdapter` | `services/ledger/legacy/legacy_crypto_processing_adapter.py` | E |
| `LegacyCryptoRpcAdapter` | `services/ledger/legacy/legacy_crypto_rpc_adapter.py` | E |

---

## 5. Supporting Domains — STUB

| Port | File | Methods |
|------|------|---------|
| AgreementPort | `services/agreement/agreement_port.py` | `create_agreement`, `get_agreement`, `record_signature`, `supersede`, `list_customer_agreements`, `get_current_terms_version` |
| CasePort | `services/case_management/case_port.py` | `create_case`, `get_case`, `resolve_case`, `update_case`, `close_case`, `list_cases`, `health` |
| ConfigPort | `services/config/config_port.py` | `get_product`, `list_products`, `get_fee`, `get_limits` |
| CustomerPort | `services/customer/customer_port.py` | `create_customer`, `get_customer`, `update_risk_level`, `transition_lifecycle`, `add_ubo` |
| FraudPort | `services/fraud/fraud_port.py` | `score`, `health` |
| HITLPort | `services/hitl/hitl_port.py` | `enqueue`, `get_case`, `list_queue`, `decide`, `stats` |
| IAMPort | `services/iam/iam_port.py` | `authenticate`, `validate_token`, `authorize`, `health` |
| NotificationPort | `services/notifications/notification_port.py` | `send`, `get_delivery_status`, `health` |
| ReconPort | `services/recon/recon_port.py` | `get_client_fund_balances`, `get_safeguarding_balances` |
| ConsumerDutyPort | `services/consumer_duty/consumer_duty_port.py` | `assess_vulnerability`, `get_vulnerability`, `assess_fair_value`, `record_outcome`, `generate_report` |

---

## 6. Freeze Policy

- **FROZEN** ports: any signature change (add/remove/rename parameter, change return type)
  requires a new ADR and a PR that bumps the minor version in the port's docstring.
- **ACTIVE** ports: in-sprint changes allowed; freeze on merge to main.
- **STUB** ports: signature changes allowed without ADR; must update this document.
- Duplicate business logic (jurisdiction blocking, EDD thresholds) lives in
  `services/compliance/legacy/_jurisdictions.py` and `services/compliance/legacy/_edd.py`.
  Changes there are breaking if adapters import them — treat as FROZEN.
