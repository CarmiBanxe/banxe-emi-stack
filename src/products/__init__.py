"""Banxe EMI — Product Catalogue (GAP-014 B-emi).

EMI product definitions with FCA regulatory attributes.

Regulatory:
  - EMR 2011 Reg.4/7 — e-money definition and safeguarding
  - CASS 7.13        — segregated account requirements
  - PS22/9           — Consumer Duty fair value
"""

from .emi_products import (
    EMIProduct,
    FairValueAssessment,
    ProductCatalogue,
    ProductStatus,
    ProductType,
    RegulatoryScheme,
)

__all__ = [
    "ProductType",
    "ProductStatus",
    "RegulatoryScheme",
    "FairValueAssessment",
    "EMIProduct",
    "ProductCatalogue",
]
