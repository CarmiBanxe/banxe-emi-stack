"""
services/fx_exchange — FX & Currency Exchange service.

Phase 21 | IL-FX-01 | banxe-emi-stack

Provides real-time FX quotes, order execution, spread management, and
compliance screening for foreign exchange transactions.

Key invariants:
  - I-01: All monetary amounts use Decimal — never float.
  - I-02: Sanctioned currencies (RUB, IRR, KPW, BYR, SYP, CUC) are hard-blocked.
  - I-05: API layer serialises amounts as strings.
  - I-24: Append-only audit trail for all FX events.
  - I-27: HITL gate for orders exceeding £50,000 (MLR 2017).
"""
