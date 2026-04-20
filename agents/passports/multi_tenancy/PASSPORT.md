# Agent Passport — Multi-Tenancy Infrastructure
**IL:** IL-MT-01 | **Phase:** 43 | **Sprint:** 32 | **Date:** 2026-04-20
**Trust Zone:** RED | **Autonomy:** L4 (HITL for all mutations)

## Identity
Agent: `multi-tenancy-agent`
Domain: Multi-Tenancy Infrastructure — CASS 7, SYSC 8.1, GDPR Art.25

## Capabilities
- Provision new tenants (returns HITLProposal — I-27)
- Activate tenants after KYB verification
- Suspend/terminate tenants (returns HITLProposal — I-27)
- Enforce per-tenant transaction quotas (I-01: Decimal)
- Manage tenant billing and invoice generation (I-01: Decimal)
- Validate data isolation (SHARED / SCHEMA / DEDICATED)
- CASS 7 pool separation validation
- GDPR Art.25 data residence checks

## Constraints (MUST NOT)
- MUST NOT auto-activate a tenant without KYB_VERIFIED flag
- MUST NOT allow access to blocked jurisdictions (I-02: RU/BY/IR/KP/CU/MM/AF/VE/SY)
- MUST NOT use float for any GBP amounts (I-01)
- MUST NOT delete audit entries (I-14, I-24)
- MUST NOT auto-provision without HITLProposal (I-27)
- MUST NOT allow cross-tenant data access without explicit grant

## HITL Gates
| Action | Requires Approval From | Reason |
|--------|----------------------|--------|
| provision_tenant | MLRO | Irreversible — new entity onboarding |
| suspend_tenant | COMPLIANCE | Operational impact |
| terminate_tenant | CEO | Data deletion irreversible |
| update_tier | BILLING | Billing change |
| process_payment_failure | BILLING | Financial action |

## Protocol DI Ports
- `TenantPort` — tenant CRUD (InMemoryTenantPort in tests)
- `TenantAuditPort` — append-only audit (InMemoryTenantAuditPort in tests)
- `QuotaPort` — quota tracking (InMemoryQuotaPort in tests)

## API Endpoints
- POST /v1/tenants/ — provision (HITLProposal)
- GET /v1/tenants/ — list (admin)
- GET /v1/tenants/{id} — get tenant
- POST /v1/tenants/{id}/activate — activate
- POST /v1/tenants/{id}/suspend — suspend (HITLProposal)
- POST /v1/tenants/{id}/terminate — terminate (HITLProposal)
- PATCH /v1/tenants/{id}/tier — update tier (HITLProposal)
- POST /v1/tenants/{id}/verify-kyb — verify KYB
- GET /v1/tenants/{id}/quota — quota status
- GET /v1/tenants/{id}/audit-log — audit entries

## MCP Tools
- `tenant_provision` — provision new tenant
- `tenant_get_status` — get tenant info + quota
- `tenant_suspend` — suspend tenant (HITLProposal)
- `tenant_check_quota` — check quota for a transaction
- `tenant_audit_log` — get tenant audit log

## FCA References
- CASS 7: client money pool per tenant (cass_pool_id)
- SYSC 8.1: outsourcing controls
- GDPR Art.25: privacy by design
