"""services/auth/legacy/ — adapter seam scaffold for BANXE.RAR auth fragments.

Wave A backend adapter seam (Phase 4). Files in this package are *scaffold-only*
boundary modules; production wiring is added in subsequent PRs once REWRITE
fragments are imported behind ports (TokenManagerPort / IAMPort / TwoFactorPort).

Canon: ADR-015 (auth ports) + AUTH_IMPORT_ORDER.md (router stays transport-only).
"""
