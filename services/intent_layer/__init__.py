"""
services/intent_layer — ADR-049 L1 Intent Layer (client intent → L2 agent dispatch)
IL-126-INTENT-LAYER-CLIENT-MASKS-2026-06-07 | banxe-emi-stack

The CLIENT-facing L1 Intent Layer specified by ADR-049: capture a free-form client
intent, classify it DETERMINISTICALLY against the S3 intent→process map, resolve it to a
canonical process_ref = {process_id, version} (ADR-048), select the client-facing mask,
and dispatch to the L2 agent through an injected port.

NOT the same layer as services/agent_routing (ADR-021), which is the INTERNAL
compliance/AML/KYC task-router to tier workers. This layer:
  - is gated by INTENT_LAYER_ENABLED  (DISTINCT from ADR-021's AGENT_ROUTING_ENABLED);
  - is cross-repo (dispatches to agents in payment-core AND emi-stack) via injected
    ports, with NO hard dependency on either agent repo's internals;
  - treats an intent that resolves to no process as a governance event, never improvised.

Composition example (wiring is composition-root work, not done in this package)::

    catalog = IntentCatalog.from_files(MAP_PATH, REGISTRY_PATH)
    enabled = intent_layer_enabled()
    classifier = IntentClassifier(catalog, enabled=enabled, llm=my_s1_llm_port)
    router = IntentRouter(my_agent_dispatch_port, enabled=enabled)

    resolved = classifier.classify("send money to Alice")
    disposition = router.route(resolved)
"""

from __future__ import annotations

from services.intent_layer.catalog import IntentCatalog, UnresolvableProcessError
from services.intent_layer.classifier import IntentClassifier
from services.intent_layer.config import (
    INTENT_LAYER_ENABLED_ENV,
    intent_layer_enabled,
)
from services.intent_layer.models import (
    ConfidenceBand,
    Disposition,
    DispositionKind,
    IntentDefinition,
    IntentStatus,
    MatchSource,
    ProcessRef,
    ResolvedIntent,
)
from services.intent_layer.ports import (
    AgentDispatchPort,
    DispatchReceipt,
    DispatchRequest,
    LLMClassification,
    LLMClassifierPort,
    NullLLMClassifier,
)
from services.intent_layer.router import IntentRouter

__all__ = [
    "INTENT_LAYER_ENABLED_ENV",
    "AgentDispatchPort",
    "ConfidenceBand",
    "Disposition",
    "DispositionKind",
    "DispatchReceipt",
    "DispatchRequest",
    "IntentCatalog",
    "IntentClassifier",
    "IntentDefinition",
    "IntentRouter",
    "IntentStatus",
    "LLMClassification",
    "LLMClassifierPort",
    "MatchSource",
    "NullLLMClassifier",
    "ProcessRef",
    "ResolvedIntent",
    "UnresolvableProcessError",
    "intent_layer_enabled",
]
