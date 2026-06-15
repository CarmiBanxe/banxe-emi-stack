"""Lead-scoring domain (ORG-STRUCTURE §2.8 Front Office / Sales, IL-190).

Houses the governed READ-ONLY :class:`~services.lead_scoring.lead_signal_port.LeadSignalPort`
CONTRACT (behavioral lead scoring, signup → active). No mutating surface lives here — the
LeadScoringAgent reads behavioral lead signals through this port only.
"""

from __future__ import annotations
