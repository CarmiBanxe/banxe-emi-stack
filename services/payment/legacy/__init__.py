"""
services/payment/legacy — REWRITE-1 adapters for PaymentRailPort (Wave C).

Semantic rewrites of NestJS TypeScript payment services (banxe-common origin):
  sepa-service/create-outgoing-transactions → LegacySepaAdapter
  banxe-transactions/payment-transaction    → LegacyTransactionsAdapter
  banxe-fiat-backend/abs-customer-payment  → LegacyAbsPaymentAdapter

Transport dropped per ADR-025 §15-16:
  - GCP Bifrost XML (abs-api requestToGCPProcessing)
  - DWH payment gRPC microservice
  - Redis cron / NestJS EventEmitter

All adapters implement PaymentRailPort (services.payment.payment_rail_port).
In-memory backends; Redis adapter deferred to Wave D.

Canon: ADR-025 §15-16 + PaymentRailPort + SESSION-2026-05-07-WAVE-C-PAYMENTS-START
"""
