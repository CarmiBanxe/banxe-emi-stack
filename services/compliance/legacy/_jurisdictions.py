"""
services/compliance/legacy/_jurisdictions.py — Shared jurisdiction blocking (I-02).

Single source of truth for FCA/OFSI/OFAC sanctioned jurisdictions.
All KYC legacy adapters import from here — never inline the set.

Canon: ADR-025 §15-16 | I-02 | services.kyc.kyc_port
"""

from __future__ import annotations

# I-02: hard-blocked jurisdictions — RU/BY/IR/KP/CU/MM/AF/VE/SY
BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)


def is_blocked(country: str) -> bool:
    """Return True if the ISO-3166-1 alpha-2 country code is on the sanctions list (I-02)."""
    return country.upper() in BLOCKED_JURISDICTIONS
