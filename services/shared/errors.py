"""
services/shared/errors.py — Shared base error for all Banxe legacy adapters.

BanxeLegacyAdapterError unifies the error hierarchy across Wave C / Wave D / Wave E
legacy adapters (F-03 audit finding). All domain-specific adapter errors inherit from
this class so callers can catch at any granularity:

    except TransactionApplicationError: ...   # specific (unchanged)
    except BanxeLegacyAdapterError: ...       # any legacy adapter error
    except Exception: ...                     # fallback (unchanged)

All adapter errors carry a machine-readable `code` attribute alongside the human-readable
message so API layers can map to HTTP status codes without string-parsing.
"""

from __future__ import annotations


class BanxeLegacyAdapterError(Exception):
    """Base error for all Banxe legacy adapter domain errors.

    Args:
        message: Human-readable description of the failure.
        code: Machine-readable error code (snake_case).
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code
