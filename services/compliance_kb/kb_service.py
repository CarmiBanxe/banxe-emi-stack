"""
services/compliance_kb/kb_service.py — Compliance Knowledge Base Service
IL-CKS-01 | banxe-emi-stack

Orchestrates the ingestion pipeline, vector store, and RAG query logic.
Used by: api/routers/compliance_kb.py and banxe_mcp/server.py (via API).
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path
from typing import Any

import yaml

from services.compliance_kb.embeddings.embedding_service import (
    EmbeddingServiceProtocol,
    InMemoryEmbeddingService,
    make_embedding_service,
)
from services.compliance_kb.ingestion.chunker import chunk_text
from services.compliance_kb.ingestion.markdown_parser import parse_markdown_text
from services.compliance_kb.ingestion.pdf_parser import parse_pdf
from services.compliance_kb.storage.chroma_store import (
    ChromaDBStore,
    ChromaStoreProtocol,
    InMemoryChromaStore,
)
from services.compliance_kb.storage.models import (
    Citation,
    DocumentChunk,
    IngestRequest,
    IngestResult,
    Jurisdiction,
    KBQueryRequest,
    KBQueryResult,
    KBSearchRequest,
    KBSearchResult,
    NotebookMetadata,
    NotebookSource,
    SourceType,
    VersionChange,
    VersionCompareRequest,
    VersionCompareResult,
)

logger = logging.getLogger("banxe.compliance_kb")


class ComplianceKBService:
    """Central service for the compliance knowledge base.

    Supports:
    - Document ingestion (PDF, Markdown, text, URL content)
    - Notebook management (pre-configured + dynamic)
    - RAG query with citations
    - Semantic search
    - Regulatory version comparison

    Uses Protocol DI for storage and embeddings — swappable in tests.
    """

    def __init__(
        self,
        store: ChromaStoreProtocol | None = None,
        embedding_service: EmbeddingServiceProtocol | None = None,
        config_path: str | None = None,
    ) -> None:
        self._store: ChromaStoreProtocol = store or InMemoryChromaStore()
        self._embedder: EmbeddingServiceProtocol = embedding_service or InMemoryEmbeddingService()
        self._notebooks: dict[str, NotebookMetadata] = {}
        self._load_notebooks(config_path)

    # ── Notebook management ────────────────────────────────────────────────

    def list_notebooks(
        self,
        tags: list[str] | None = None,
        jurisdiction: str | None = None,
    ) -> list[NotebookMetadata]:
        """List all notebooks, optionally filtered by tags or jurisdiction."""
        notebooks = list(self._notebooks.values())
        if tags:
            tag_set = set(tags)
            notebooks = [nb for nb in notebooks if tag_set & set(nb.tags)]
        if jurisdiction:
            notebooks = [nb for nb in notebooks if nb.jurisdiction.value == jurisdiction]
        return notebooks

    def get_notebook(self, notebook_id: str) -> NotebookMetadata | None:
        """Return notebook metadata including source list."""
        nb = self._notebooks.get(notebook_id)
        if nb is None:
            return None
        # Refresh doc_count from store
        nb.doc_count = self._store.get_chunk_count(notebook_id)
        return nb

    # ── Ingestion ──────────────────────────────────────────────────────────

    def ingest(self, request: IngestRequest) -> IngestResult:
        """Ingest a document into a notebook's vector store.

        Supports:
        - Text content (request.content)
        - PDF file (request.file_path with .pdf extension)
        - Markdown file (request.file_path with .md extension)
        - Plain text file (request.file_path with .txt extension)

        Does NOT support URL ingestion directly (use url_scraper async).
        """
        if request.notebook_id not in self._notebooks:
            raise ValueError(f"Notebook '{request.notebook_id}' not found")

        chunks: list[DocumentChunk] = []
        meta: dict[str, Any] = {
            "jurisdiction": request.jurisdiction.value,
            "source_type": request.source_type.value,
            "version": request.version,
            "tags": ",".join(request.tags),
        }

        if request.content:
            chunks = chunk_text(
                text=request.content,
                document_id=request.document_id,
                metadata=meta,
            )
        elif request.file_path:
            path = Path(request.file_path)
            suffix = path.suffix.lower()
            if suffix == ".pdf":
                chunks = parse_pdf(request.file_path, request.document_id, meta)
            elif suffix in (".md", ".mdx"):
                text = path.read_text(encoding="utf-8")
                chunks = parse_markdown_text(text, request.document_id, meta)
            elif suffix == ".txt":
                text = path.read_text(encoding="utf-8")
                chunks = chunk_text(text, request.document_id, metadata=meta)
            else:
                raise ValueError(f"Unsupported file type: {suffix}")
        else:
            raise ValueError("Either 'content' or 'file_path' must be provided")

        if not chunks:
            return IngestResult(
                document_id=request.document_id,
                notebook_id=request.notebook_id,
                chunks_created=0,
                status="no_content",
            )

        embeddings = self._embedder.embed_batch([c.text for c in chunks])
        self._store.add_chunks(request.notebook_id, chunks, embeddings)

        logger.info(
            "Ingested document=%s into notebook=%s chunks=%d",
            request.document_id,
            request.notebook_id,
            len(chunks),
        )
        return IngestResult(
            document_id=request.document_id,
            notebook_id=request.notebook_id,
            chunks_created=len(chunks),
            status="ok",
        )

    # ── RAG Query ──────────────────────────────────────────────────────────

    def query(self, request: KBQueryRequest) -> KBQueryResult:
        """RAG query: retrieve relevant chunks and synthesise an answer.

        Returns the answer with citations (source, section, snippet).
        When an LLM is not available, returns a structured summary of
        the top retrieved chunks as the answer.
        """
        if request.notebook_id not in self._notebooks:
            raise ValueError(f"Notebook '{request.notebook_id}' not found")

        q_embedding = self._embedder.embed_single(request.question)
        results = self._store.query(
            collection_name=request.notebook_id,
            embedding=q_embedding,
            n_results=request.max_citations,
        )

        if not results:
            return KBQueryResult(
                question=request.question,
                answer="No relevant content found in the knowledge base for this query.",
                citations=[],
                notebook_id=request.notebook_id,
                confidence=0.0,
            )

        nb = self._notebooks[request.notebook_id]
        citations = self._build_citations(results, nb)
        answer = self._synthesise_answer(request.question, results, citations)
        confidence = results[0].score if results else 0.0

        return KBQueryResult(
            question=request.question,
            answer=answer,
            citations=citations[: request.max_citations],
            notebook_id=request.notebook_id,
            confidence=confidence,
        )

    # ── Semantic Search ────────────────────────────────────────────────────

    def search(self, request: KBSearchRequest) -> list[KBSearchResult]:
        """Semantic search over a notebook. Returns raw chunks with scores."""
        if request.notebook_id not in self._notebooks:
            raise ValueError(f"Notebook '{request.notebook_id}' not found")

        q_embedding = self._embedder.embed_single(request.query)
        return self._store.query(
            collection_name=request.notebook_id,
            embedding=q_embedding,
            n_results=request.limit,
        )

    # ── Version Comparison ─────────────────────────────────────────────────

    def compare_versions(self, request: VersionCompareRequest) -> VersionCompareResult:
        """Compare two versions of a regulatory document.

        Searches both version tags and summarises differences.
        Returns structured changes with section, type, and impact tags.
        """
        # Search for content tagged with from_version and to_version
        from_q = self._embedder.embed_single(f"version:{request.from_version} {request.source_id}")
        to_q = self._embedder.embed_single(f"version:{request.to_version} {request.source_id}")

        # Find notebooks containing this source
        target_notebooks = [
            nb_id
            for nb_id, nb in self._notebooks.items()
            if any(s.id == request.source_id for s in nb.sources)
        ]

        from_chunks: list[KBSearchResult] = []
        to_chunks: list[KBSearchResult] = []

        for nb_id in target_notebooks:
            from_chunks.extend(self._store.query(nb_id, from_q, n_results=5))
            to_chunks.extend(self._store.query(nb_id, to_q, n_results=5))

        changes = _diff_version_chunks(from_chunks, to_chunks, request.focus_sections)

        summary = (
            f"Comparing {request.source_id} from {request.from_version} "
            f"to {request.to_version}. "
            f"Found {len(changes)} changes"
            + (
                f" in sections: {', '.join(request.focus_sections)}"
                if request.focus_sections
                else ""
            )
            + "."
        )

        return VersionCompareResult(
            source_id=request.source_id,
            from_version=request.from_version,
            to_version=request.to_version,
            diff_summary=summary,
            changes=changes,
        )

    # ── Citation helpers ───────────────────────────────────────────────────

    def _build_citations(
        self,
        results: list[KBSearchResult],
        notebook: NotebookMetadata,
    ) -> list[Citation]:
        citations: list[Citation] = []
        seen: set[str] = set()

        source_map = {s.id: s for s in notebook.sources}

        for result in results:
            doc_id = result.document_id
            if doc_id in seen:
                continue
            seen.add(doc_id)

            source = source_map.get(doc_id)
            citations.append(
                Citation(
                    source_id=doc_id,
                    source_type=source.source_type if source else SourceType.GUIDANCE,
                    title=source.name if source else doc_id,
                    section=result.section,
                    snippet=result.text[:300],
                    uri=source.url if source else None,
                    version=source.version if source else "unknown",
                )
            )
        return citations

    def _synthesise_answer(
        self,
        question: str,
        results: list[KBSearchResult],
        citations: list[Citation],
    ) -> str:
        """Build a structured answer from retrieved chunks.

        In production this would call an LLM with the retrieved context.
        Without an LLM, returns a formatted summary of the top chunks.
        """
        lines = [
            f"Based on the compliance knowledge base, here is what was found for: '{question}'",
            "",
        ]
        for i, result in enumerate(results[:5], 1):
            snippet = textwrap.shorten(result.text, width=400, placeholder="...")
            lines.append(f"[{i}] {result.section}: {snippet}")
            lines.append("")

        if citations:
            lines.append("Sources:")
            for cit in citations[:5]:
                lines.append(f"  - {cit.title} (§{cit.section}) [{cit.version}]")

        return "\n".join(lines)

    # ── Notebook config loading ────────────────────────────────────────────

    def _load_notebooks(self, config_path: str | None) -> None:
        """Load pre-configured notebooks from YAML."""
        paths_to_try = [
            config_path,
            "config/compliance_notebooks.yaml",
            Path(__file__).parent.parent.parent / "config" / "compliance_notebooks.yaml",
        ]
        for p in paths_to_try:
            if p and Path(p).exists():
                self._parse_notebook_config(Path(p))
                return

        logger.warning("No compliance_notebooks.yaml found — starting with empty KB")

    def _parse_notebook_config(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        for nb_id, nb_data in raw.get("notebooks", {}).items():
            sources = [
                NotebookSource(
                    id=s["id"],
                    name=s["name"],
                    source_type=SourceType(s.get("type", "guidance")),
                    url=s.get("url"),
                    version=s.get("version", "latest"),
                )
                for s in nb_data.get("sources", [])
            ]
            self._notebooks[nb_id] = NotebookMetadata(
                id=nb_id,
                name=nb_data["name"],
                description=nb_data.get("description", ""),
                tags=nb_data.get("tags", []),
                jurisdiction=Jurisdiction(nb_data.get("jurisdiction", "eu")),
                sources=sources,
                doc_count=0,
            )

        logger.info("Loaded %d compliance notebooks from %s", len(self._notebooks), path)


# ── Version diff helper ────────────────────────────────────────────────────


def _diff_version_chunks(
    from_chunks: list[KBSearchResult],
    to_chunks: list[KBSearchResult],
    focus_sections: list[str],
) -> list[VersionChange]:
    """Produce a list of VersionChange objects by comparing chunk sections."""
    from_sections = {c.section: c.text for c in from_chunks}
    to_sections = {c.section: c.text for c in to_chunks}

    all_sections = set(from_sections) | set(to_sections)
    if focus_sections:
        all_sections = {s for s in all_sections if any(f in s for f in focus_sections)}

    changes: list[VersionChange] = []
    for section in sorted(all_sections):
        before = from_sections.get(section)
        after = to_sections.get(section)

        if before is None and after is not None:
            changes.append(
                VersionChange(
                    section=section,
                    change_type="added",
                    after=after[:300],
                    impact_tags=["new-requirement"],
                )
            )
        elif before is not None and after is None:
            changes.append(
                VersionChange(
                    section=section,
                    change_type="removed",
                    before=before[:300],
                    impact_tags=["removed-requirement"],
                )
            )
        elif before != after:
            changes.append(
                VersionChange(
                    section=section,
                    change_type="modified",
                    before=(before or "")[:200],
                    after=(after or "")[:200],
                    impact_tags=["modified-requirement"],
                )
            )

    return changes


# ── Singleton factory ──────────────────────────────────────────────────────

_default_service: ComplianceKBService | None = None


def get_kb_service() -> ComplianceKBService:
    """Return the singleton ComplianceKBService (production config)."""
    global _default_service
    if _default_service is None:
        import os

        persist_dir = os.environ.get("CHROMA_PERSIST_DIR", "data/compliance_kb/chroma")
        Path(persist_dir).mkdir(parents=True, exist_ok=True)

        store = ChromaDBStore(persist_dir)
        embedder = make_embedding_service()
        _default_service = ComplianceKBService(
            store=store,
            embedding_service=embedder,
        )
    return _default_service
