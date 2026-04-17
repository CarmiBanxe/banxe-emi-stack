| old path | new path | status | action | caller | role | notes |
|---|---|---|---|---|---|---|
| BANXE.RAR auth token logic | services/auth/token_manager.py | target | attach/import behind port | api/routers/auth.py | token issuance + refresh | router currently duplicates JWT logic |
| BANXE.RAR auth entry flow | api/routers/auth.py | dirty boundary | thin router only | external HTTP clients | HTTP transport layer | keep transport, move business logic out |
| BANXE.RAR SCA flow | services/auth/sca_service.py | candidate | map/import selectively | auth router / SCA endpoints | PSD2 SCA orchestration | existing tested service boundary |
| BANXE.RAR 2FA flow | services/auth/two_factor.py | candidate | map/import selectively | sca/auth service layer | OTP/TOTP factor handling | stronger than token layer today |
| BANXE.RAR IAM integration | services/iam/iam_port.py | target contract | attach adapter | auth/services layer | IAM boundary | best current contract |
