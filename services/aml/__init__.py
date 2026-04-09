# ─── BANXE COMPLIANCE RAG (auto-injected) ───
try:
    import sys as _sys

    _sys.path.insert(0, "/data/compliance")
    from compliance_agent_client import rag_context as _rag_context

    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

    def _rag_context(agent, query, k=3):
        return ""


def get_compliance_context(query, agent_name=None, k=3):
    """Получить compliance-контекст из базы знаний для промпта."""
    if not _RAG_AVAILABLE:
        return ""
    return _rag_context(agent_name or "banxe_aml_screening_agent", query, k)


# ─────────────────────────────────────────────
