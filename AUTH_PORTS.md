# Auth/IAM Ports

## TokenManagerPort
Purpose: issue access tokens, validate refresh tokens, rotate token pairs
Caller: auth router
Rule: router must not encode/decode JWT directly

## ScaServicePort
Purpose: initiate challenge, verify challenge, resend challenge, list methods
Caller: auth router
Rule: SCA policy stays in service layer

## TwoFactorPort
Purpose: OTP/TOTP generation and verification
Caller: SCA service
Rule: factor-specific logic stays below SCA orchestration

## IAMPort
Purpose: external/internal IAM identity operations
Caller: auth domain services
Rule: imported IAM logic attaches as adapter, not inside router
