# AUTH_MATRIX

| Component | Current role | Inline/domain/integration logic | Existing seam | Target boundary | BANXE.RAR attach point | Notes |
|---|---|---|---|---|---|---|
| api/routers/auth.py | Inbound adapter | Transport + residual auth mapping | HTTP endpoints | Request/response only | No direct import | Router must stay thin |
| services/auth/auth_application_service.py | Application service | Login/refresh orchestration | TokenManagerPort, iam_port, sca_service | Main auth use-case boundary | Maybe via ports only | Good extraction anchor |
| services/auth/token_manager.py | Token adapter/service | Token issue/validate logic | TokenManagerPort | Outbound token boundary | Preferred adapter seam | Validate reuse first |
| services/auth/sca_service.py | Auth-support service | SCA flow logic | sca_service_port | Outbound/domain-support boundary | Selective | Preserve tested contour |
| services/auth/two_factor.py | Auth-support service | 2FA logic | two_factor_port | Outbound/domain-support boundary | Selective | Preserve tested contour |
| services/iam/iam_port.py | Port contract | IAM abstraction | Existing port | Outbound IAM boundary | Preferred | Strongest current contract |
