# ADR-015: Auth Domain Ports Formalization

## Status
Accepted — 2026-04-22

## Context
Canon (AUTH_PORTS.md) requires hexagonal ports for TokenManager, SCAService, TwoFactor, IAM so that BANXE.RAR and future IAM providers (Keycloak) attach as adapters behind Protocols, not by modifying core services.

## Decision
Four Protocol-based ports formalized:

| Port | Location | Concrete Impl | Contract Test |
|---|---|---|---|
| TokenManagerPort | services/auth/token_manager_port.py | TokenManager | tests/test_token_manager_port.py |
| ScaServicePort | services/auth/sca_service_port.py | SCAService | tests/test_sca_service_port.py |
| TwoFactorPort | services/auth/two_factor_port.py | TOTPService | tests/test_two_factor_port.py |
| IAMPort | services/iam/iam_port.py | MockIAMAdapter | (existing) |

## Canonical Signatures

### TokenManagerPort
- issue_access_token(customer_id) -> (str, datetime)
- issue_refresh_token(customer_id) -> (str, datetime)
- validate_access_token(token) -> dict
- validate_refresh_token(token) -> dict
- is_inactive(last_activity) -> bool
- rotate(refresh_token) -> (str, str, datetime, datetime)

### ScaServicePort
- create_challenge(customer_id, transaction_id, method, amount=None, payee=None) -> SCAChallenge
- verify(challenge_id, otp_code=None, biometric_proof=None) -> SCAVerifyResult
- resend_challenge(challenge_id) -> SCAChallenge
- get_methods(customer_id) -> SCAMethods
- register_otp_secret(customer_id, secret) -> None

### TwoFactorPort
- setup_totp(customer_id, account_name=None) -> TOTPSetup
- confirm_totp(customer_id, otp) -> bool
- is_enabled(customer_id) -> bool
- verify_totp(customer_id, otp) -> VerifyResult
- verify_backup_code(customer_id, code) -> VerifyResult
- revoke_totp(customer_id) -> None
- backup_codes_remaining(customer_id) -> int

## Rules
- Router must not encode/decode JWT directly (use TokenManagerPort).
- SCA policy stays in service layer (router uses ScaServicePort).
- Factor-specific logic stays below SCA orchestration (TwoFactorPort).
- Imported IAM logic attaches as adapter, not inside router (IAMPort).
- Ad-hoc sed replacements without grep+compile+tests gate are forbidden.

## Consequences
- BANXE.RAR adapters implement Protocols, no core modifications.
- Keycloak adapter implements IAMPort when available.
- Contract tests prevent drift.
