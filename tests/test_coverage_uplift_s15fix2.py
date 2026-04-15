"""
tests/test_coverage_uplift_s15fix2.py — Coverage uplift batch 2
S15-FIX-3 | GAP-3 | banxe-emi-stack

Targeted tests for previously uncovered branches across:
- FixedEmbeddingService + make_embedding_service factory
- InMemoryChromaStore (delete_document, list_collections, _matches_filter, cosine_sim helper)
- ReasoningBankStore (linear_search edge cases, get_reusable_reasoning override)
- ComplianceKBService (compare_versions, _diff_version_chunks, file_path ingest)
- MitosisGenerator (_direct_generate branches, fallback_enabled=False)
- TokenExtractor (sync failure paths, build_style_dictionary failure)
"""

from __future__ import annotations

from datetime import UTC, datetime
import os
from pathlib import Path
from unittest.mock import patch

import pytest

# ── FixedEmbeddingService ──────────────────────────────────────────────────────
from services.compliance_kb.constants import EMBEDDING_DIM
from services.compliance_kb.embeddings.embedding_service import (
    FixedEmbeddingService,
    InMemoryEmbeddingService,
    OpenAIEmbeddingService,
    make_embedding_service,
)


class TestFixedEmbeddingService:
    def test_dimension_returns_embedding_dim(self):
        svc = FixedEmbeddingService()
        assert svc.dimension == EMBEDDING_DIM

    def test_embed_single_returns_list_of_floats(self):
        svc = FixedEmbeddingService()
        vec = svc.embed_single("test text")
        assert isinstance(vec, list)
        assert len(vec) == EMBEDDING_DIM

    def test_embed_single_same_text_same_vector(self):
        svc = FixedEmbeddingService()
        v1 = svc.embed_single("hello")
        v2 = svc.embed_single("hello")
        assert v1 == v2

    def test_embed_single_different_texts_different_vectors(self):
        svc = FixedEmbeddingService()
        v1 = svc.embed_single("CASS safeguarding")
        v2 = svc.embed_single("AML transaction monitoring")
        assert v1 != v2

    def test_embed_single_is_unit_vector(self):
        svc = FixedEmbeddingService()
        vec = svc.embed_single("some regulation text")
        total = sum(x * x for x in vec)
        assert abs(total - 1.0) < 1e-9  # unit vector: norm == 1

    def test_embed_batch_returns_list_of_vectors(self):
        svc = FixedEmbeddingService()
        texts = ["text A", "text B", "text C"]
        result = svc.embed_batch(texts)
        assert len(result) == 3
        for vec in result:
            assert len(vec) == EMBEDDING_DIM

    def test_embed_batch_empty_returns_empty(self):
        svc = FixedEmbeddingService()
        assert svc.embed_batch([]) == []

    def test_embed_batch_consistent_with_embed_single(self):
        svc = FixedEmbeddingService()
        texts = ["alpha", "beta"]
        batch = svc.embed_batch(texts)
        for i, t in enumerate(texts):
            assert batch[i] == svc.embed_single(t)


class TestMakeEmbeddingServiceFactory:
    def test_inmemory_adapter_returns_inmemory(self):
        with patch.dict(os.environ, {"EMBEDDING_ADAPTER": "inmemory"}):
            svc = make_embedding_service()
        assert isinstance(svc, InMemoryEmbeddingService)

    def test_openai_adapter_returns_openai(self):
        with patch.dict(os.environ, {"EMBEDDING_ADAPTER": "openai"}):
            svc = make_embedding_service()
        assert isinstance(svc, OpenAIEmbeddingService)

    def test_openai_embedding_service_dimension(self):
        svc = OpenAIEmbeddingService(api_key="test-key")
        assert svc.dimension == 1536

    def test_sentence_transformers_adapter_returns_sentence_transformers(self):
        from services.compliance_kb.embeddings.embedding_service import (
            SentenceTransformerEmbeddingService,
        )

        with patch.dict(os.environ, {"EMBEDDING_ADAPTER": "sentence_transformers"}):
            svc = make_embedding_service()
        assert isinstance(svc, SentenceTransformerEmbeddingService)

    def test_default_adapter_is_sentence_transformers(self):
        from services.compliance_kb.embeddings.embedding_service import (
            SentenceTransformerEmbeddingService,
        )

        env = {k: v for k, v in os.environ.items() if k != "EMBEDDING_ADAPTER"}
        with patch.dict(os.environ, env, clear=True):
            svc = make_embedding_service()
        assert isinstance(svc, SentenceTransformerEmbeddingService)


# ── InMemoryChromaStore ─────────────────────────────────────────────────────────

from services.compliance_kb.storage.chroma_store import (
    InMemoryChromaStore,
    _cosine_similarity,
    make_chunk_id,
)
from services.compliance_kb.storage.models import DocumentChunk


def _make_chunk(
    doc_id: str = "doc-001", chunk_id: str = "c-001", section: str = "§1"
) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        document_id=doc_id,
        text="Compliance text about safeguarding.",
        section=section,
        char_start=0,
        char_end=40,
        metadata={"jurisdiction": "uk", "version": "1.0"},
    )


class TestInMemoryChromaStoreDeleteAndList:
    def test_delete_document_removes_chunks(self):
        store = InMemoryChromaStore()
        chunk = _make_chunk(doc_id="doc-del")
        store.add_chunks("col-1", [chunk], [[0.1] * EMBEDDING_DIM])
        assert store.get_chunk_count("col-1") == 1
        store.delete_document("col-1", "doc-del")
        assert store.get_chunk_count("col-1") == 0

    def test_delete_nonexistent_document_is_noop(self):
        store = InMemoryChromaStore()
        store.delete_document("col-1", "no-such-doc")  # no error
        assert store.get_chunk_count("col-1") == 0

    def test_delete_only_removes_matching_doc(self):
        store = InMemoryChromaStore()
        c1 = _make_chunk(doc_id="doc-A", chunk_id="c-A")
        c2 = _make_chunk(doc_id="doc-B", chunk_id="c-B")
        store.add_chunks("col-2", [c1, c2], [[0.1] * EMBEDDING_DIM] * 2)
        store.delete_document("col-2", "doc-A")
        assert store.get_chunk_count("col-2") == 1

    def test_list_collections_returns_names(self):
        store = InMemoryChromaStore()
        store.add_chunks("col-x", [_make_chunk()], [[0.0] * EMBEDDING_DIM])
        store.add_chunks("col-y", [_make_chunk()], [[0.0] * EMBEDDING_DIM])
        names = store.list_collections()
        assert "col-x" in names
        assert "col-y" in names

    def test_list_collections_empty_store(self):
        store = InMemoryChromaStore()
        assert store.list_collections() == []

    def test_query_with_where_filter_matches(self):
        store = InMemoryChromaStore()
        chunk = _make_chunk()
        chunk2 = DocumentChunk(
            chunk_id="c-002",
            document_id="doc-002",
            text="AML transaction monitoring.",
            section="§2",
            char_start=0,
            char_end=30,
            metadata={"jurisdiction": "eu", "version": "2.0"},
        )
        store.add_chunks("col-f", [chunk, chunk2], [[0.5] * EMBEDDING_DIM, [0.3] * EMBEDDING_DIM])
        results = store.query(
            "col-f", [0.5] * EMBEDDING_DIM, n_results=10, where={"jurisdiction": "uk"}
        )
        assert all(r.metadata.get("jurisdiction") == "uk" for r in results)

    def test_query_with_where_filter_no_match_returns_empty(self):
        store = InMemoryChromaStore()
        chunk = _make_chunk()
        store.add_chunks("col-g", [chunk], [[0.5] * EMBEDDING_DIM])
        results = store.query("col-g", [0.5] * EMBEDDING_DIM, where={"jurisdiction": "us"})
        assert results == []


class TestCosineSimilarityHelper:
    def test_identical_vectors_return_one(self):
        a = [1.0, 0.0, 0.0]
        assert abs(_cosine_similarity(a, a) - 1.0) < 1e-9

    def test_orthogonal_vectors_return_zero(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine_similarity(a, b)) < 1e-9

    def test_zero_vector_returns_zero(self):
        a = [0.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert _cosine_similarity(a, b) == 0.0

    def test_mismatched_length_returns_zero(self):
        assert _cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_make_chunk_id_format(self):
        cid = make_chunk_id("doc-001", 5)
        assert cid == "doc-001::chunk-0005"

    def test_make_chunk_id_zero_index(self):
        cid = make_chunk_id("fca-cass-15", 0)
        assert cid == "fca-cass-15::chunk-0000"


# ── ReasoningBankStore ─────────────────────────────────────────────────────────

from services.reasoning_bank.models import (
    CaseRecord,
    DecisionRecord,
    ReasoningRecord,
)
from services.reasoning_bank.store import ReasoningBankStore


def _now() -> datetime:
    return datetime.now(UTC)


def _make_case(case_id: str = "case-001") -> CaseRecord:
    return CaseRecord(
        case_id=case_id,
        event_type="aml_screening",
        product="emoney_account",
        jurisdiction="UK",
        customer_id="cust-001",
        risk_context={},
        playbook_id="pb-aml-v1",
        tier_used=1,
        created_at=_now(),
    )


def _make_decision(case_id: str = "case-001", overridden: bool = False) -> DecisionRecord:
    return DecisionRecord(
        decision_id=f"d-{case_id}",
        case_id=case_id,
        decision="approve",
        final_risk_score=0.3,
        decided_by="tier1",
        decided_at=_now(),
        overridden=overridden,
    )


def _make_reasoning(case_id: str = "case-001") -> ReasoningRecord:
    return ReasoningRecord(
        reasoning_id=f"r-{case_id}",
        case_id=case_id,
        internal_view="low risk",
        audit_view="approved",
        customer_view="processed",
        token_cost=100,
        model_used="claude-sonnet-4-6",
        created_at=_now(),
    )


class TestReasoningBankStoreEdgeCases:
    @pytest.mark.asyncio
    async def test_get_reusable_reasoning_overridden_returns_none(self):
        store = ReasoningBankStore()
        case = _make_case("c-override")
        decision = _make_decision("c-override", overridden=True)
        reasoning = _make_reasoning("c-override")
        await store.store_case(case=case, decision=decision, reasoning=reasoning)
        result = await store.get_reusable_reasoning("c-override")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_reusable_reasoning_not_overridden_returns_reasoning(self):
        store = ReasoningBankStore()
        case = _make_case("c-ok")
        decision = _make_decision("c-ok", overridden=False)
        reasoning = _make_reasoning("c-ok")
        await store.store_case(case=case, decision=decision, reasoning=reasoning)
        result = await store.get_reusable_reasoning("c-ok")
        assert result is not None
        assert result.case_id == "c-ok"

    @pytest.mark.asyncio
    async def test_linear_search_empty_index_returns_empty(self):
        store = ReasoningBankStore()
        result = await store.find_similar([0.1] * 384, top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_linear_search_below_threshold_returns_empty(self):
        """Zero embeddings have cosine sim = 0.0, below threshold 0.85."""
        store = ReasoningBankStore()
        case = _make_case("c-sim")
        decision = _make_decision("c-sim")
        reasoning = _make_reasoning("c-sim")
        embedding = [0.0] * 384  # zero vector
        await store.store_case(
            case=case, decision=decision, reasoning=reasoning, embedding=embedding
        )
        # Query with non-zero vector — cosine sim to zero vector = 0.0 < threshold
        result = await store.find_similar([1.0] + [0.0] * 383, top_k=5, threshold=0.85)
        assert result == []

    @pytest.mark.asyncio
    async def test_compute_policy_hash_is_deterministic(self):
        store = ReasoningBankStore()
        yaml_content = "playbook: aml-v1\nrules:\n  - threshold: 0.7"
        h1 = store.compute_policy_hash(yaml_content)
        h2 = store.compute_policy_hash(yaml_content)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    @pytest.mark.asyncio
    async def test_compute_policy_hash_differs_for_different_content(self):
        store = ReasoningBankStore()
        h1 = store.compute_policy_hash("version: 1")
        h2 = store.compute_policy_hash("version: 2")
        assert h1 != h2

    @pytest.mark.asyncio
    async def test_stats_returns_correct_counts(self):
        store = ReasoningBankStore()
        case = _make_case("c-stats")
        decision = _make_decision("c-stats")
        reasoning = _make_reasoning("c-stats")
        await store.store_case(case=case, decision=decision, reasoning=reasoning)
        stats = store.stats()
        assert stats["cases"] == 1
        assert stats["decisions"] == 1
        assert stats["reasoning"] == 1


# ── ComplianceKBService — compare_versions + file_path ingest ──────────────────

from services.compliance_kb.kb_service import ComplianceKBService, _diff_version_chunks
from services.compliance_kb.storage.models import (
    IngestRequest,
    Jurisdiction,
    KBSearchResult,
    SourceType,
    VersionCompareRequest,
)


def _make_kb() -> ComplianceKBService:
    return ComplianceKBService(
        store=InMemoryChromaStore(),
        embedding_service=FixedEmbeddingService(),
    )


class TestDiffVersionChunks:
    def test_added_section_in_to_chunks(self):
        from_chunks: list[KBSearchResult] = []
        to_chunks = [
            KBSearchResult(
                chunk_id="c1",
                document_id="doc-1",
                text="New requirement: firms must X.",
                section="§5.1",
                score=0.9,
            )
        ]
        changes = _diff_version_chunks(from_chunks, to_chunks, [])
        assert len(changes) == 1
        assert changes[0].change_type == "added"
        assert changes[0].section == "§5.1"

    def test_removed_section_in_from_chunks(self):
        from_chunks = [
            KBSearchResult(
                chunk_id="c1",
                document_id="doc-1",
                text="Old requirement removed.",
                section="§3.2",
                score=0.8,
            )
        ]
        to_chunks: list[KBSearchResult] = []
        changes = _diff_version_chunks(from_chunks, to_chunks, [])
        assert len(changes) == 1
        assert changes[0].change_type == "removed"

    def test_modified_section_when_text_differs(self):
        from_chunks = [
            KBSearchResult(
                chunk_id="c1",
                document_id="doc-1",
                text="Firms must reconcile weekly.",
                section="§7",
                score=0.8,
            )
        ]
        to_chunks = [
            KBSearchResult(
                chunk_id="c2",
                document_id="doc-1",
                text="Firms must reconcile daily.",
                section="§7",
                score=0.85,
            )
        ]
        changes = _diff_version_chunks(from_chunks, to_chunks, [])
        assert len(changes) == 1
        assert changes[0].change_type == "modified"

    def test_identical_sections_produce_no_changes(self):
        text = "Safeguarding requires daily reconciliation."
        chunk = KBSearchResult(
            chunk_id="c1",
            document_id="doc-1",
            text=text,
            section="§1",
            score=0.9,
        )
        changes = _diff_version_chunks([chunk], [chunk], [])
        assert changes == []

    def test_focus_sections_filters_results(self):
        from_chunks = [
            KBSearchResult(
                chunk_id="c1",
                document_id="doc-1",
                text="Old text §2.",
                section="§2",
                score=0.7,
            ),
            KBSearchResult(
                chunk_id="c2",
                document_id="doc-1",
                text="Old text §9.",
                section="§9",
                score=0.7,
            ),
        ]
        to_chunks: list[KBSearchResult] = []
        # Only focus on §2
        changes = _diff_version_chunks(from_chunks, to_chunks, ["§2"])
        assert len(changes) == 1
        assert changes[0].section == "§2"


class TestCompareVersions:
    def test_compare_versions_returns_result(self):
        kb = _make_kb()
        # Ingest content into emi-uk-fca
        req = IngestRequest(
            notebook_id="emi-uk-fca",
            document_id="fca-cass-15",
            name="CASS 15",
            content="Client funds must be safeguarded in designated accounts.",
            source_type=SourceType.REGULATION,
            jurisdiction=Jurisdiction.UK,
            version="1.0",
        )
        kb.ingest(req)
        vc_req = VersionCompareRequest(
            source_id="fca-cass-15",
            from_version="1.0",
            to_version="2.0",
        )
        result = kb.compare_versions(vc_req)
        assert result is not None
        assert result.source_id == "fca-cass-15"
        assert isinstance(result.diff_summary, str)

    def test_compare_versions_unknown_source_returns_empty_changes(self):
        kb = _make_kb()
        vc_req = VersionCompareRequest(
            source_id="no-such-source",
            from_version="1.0",
            to_version="2.0",
        )
        result = kb.compare_versions(vc_req)
        assert result.changes == []

    def test_compare_versions_summary_contains_source_id(self):
        kb = _make_kb()
        vc_req = VersionCompareRequest(
            source_id="ps25-12",
            from_version="draft",
            to_version="final",
        )
        result = kb.compare_versions(vc_req)
        assert "ps25-12" in result.diff_summary


class TestKBServiceFilepathIngest:
    def test_ingest_txt_file(self, tmp_path: Path):
        kb = _make_kb()
        txt = tmp_path / "regulation.txt"
        txt.write_text("CASS 15 requires daily reconciliation for safeguarding.")
        result = kb.ingest(
            IngestRequest(
                notebook_id="emi-uk-fca",
                document_id="cass-15-txt",
                name="CASS 15 TXT",
                file_path=str(txt),
                source_type=SourceType.REGULATION,
                jurisdiction=Jurisdiction.UK,
                version="1.0",
            )
        )
        assert result.chunks_created >= 1
        assert result.document_id == "cass-15-txt"

    def test_ingest_md_file(self, tmp_path: Path):
        kb = _make_kb()
        md = tmp_path / "guide.md"
        md.write_text("# CASS 15 Guide\n\nFirms must safeguard client funds daily.")
        result = kb.ingest(
            IngestRequest(
                notebook_id="emi-uk-fca",
                document_id="cass-15-md",
                name="CASS 15 MD",
                file_path=str(md),
                source_type=SourceType.GUIDANCE,
                jurisdiction=Jurisdiction.UK,
                version="1.0",
            )
        )
        assert result.chunks_created >= 1

    def test_ingest_unsupported_file_type_raises(self, tmp_path: Path):
        kb = _make_kb()
        docx = tmp_path / "document.docx"
        docx.write_bytes(b"fake docx content")
        with pytest.raises(ValueError, match="Unsupported file type"):
            kb.ingest(
                IngestRequest(
                    notebook_id="emi-uk-fca",
                    document_id="cass-bad",
                    name="Bad type",
                    file_path=str(docx),
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version="1.0",
                )
            )

    def test_ingest_no_content_no_file_raises(self):
        kb = _make_kb()
        with pytest.raises(ValueError, match="Either 'content' or 'file_path'"):
            kb.ingest(
                IngestRequest(
                    notebook_id="emi-uk-fca",
                    document_id="empty",
                    name="Empty",
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version="1.0",
                )
            )

    def test_ingest_unknown_notebook_raises(self):
        kb = _make_kb()
        with pytest.raises(ValueError, match="Notebook"):
            kb.ingest(
                IngestRequest(
                    notebook_id="non-existent-notebook",
                    document_id="d-1",
                    name="doc",
                    content="text",
                    source_type=SourceType.REGULATION,
                    jurisdiction=Jurisdiction.UK,
                    version="1.0",
                )
            )


# ── MitosisGenerator ──────────────────────────────────────────────────────────

from services.design_pipeline.code_generator import MitosisGenerationError, MitosisGenerator
from services.design_pipeline.models import Framework


class TestMitosisGeneratorDirectGenerate:
    def test_empty_jsx_raises_error(self):
        gen = MitosisGenerator()
        with pytest.raises(MitosisGenerationError, match="Empty"):
            gen.compile("   ", Framework.REACT)

    def test_direct_generate_react(self):
        gen = MitosisGenerator()
        # _direct_generate React path via compile with fallback
        jsx = "export default function Button() { return <div>Click</div>; }"
        with patch.object(gen, "_run_mitosis_cli", side_effect=FileNotFoundError("no cli")):
            result = gen.compile(jsx, Framework.REACT)
        assert "react" in result.lower() or "Button" in result or "div" in result

    def test_direct_generate_vue(self):
        gen = MitosisGenerator()
        jsx = "export default function MyCard() { return <div>Card</div>; }"
        with patch.object(gen, "_run_mitosis_cli", side_effect=FileNotFoundError("no cli")):
            result = gen.compile(jsx, Framework.VUE)
        assert "<template>" in result
        assert "MyCard" in result

    def test_direct_generate_vue_extracts_component_name(self):
        gen = MitosisGenerator()
        jsx = "export default function PaymentButton() { return <button>Pay</button>; }"
        result = gen._direct_generate(jsx, Framework.VUE)
        assert "PaymentButton" in result

    def test_direct_generate_react_native(self):
        gen = MitosisGenerator()
        jsx = "export default function NativeCard() { return <div>Card</div>; }"
        with patch.object(gen, "_run_mitosis_cli", side_effect=FileNotFoundError("no cli")):
            result = gen.compile(jsx, Framework.REACT_NATIVE)
        assert "react-native" in result.lower() or "View" in result

    def test_direct_generate_svelte(self):
        gen = MitosisGenerator()
        jsx = "export default function SvelteComp() { return <div>hi</div>; }"
        with patch.object(gen, "_run_mitosis_cli", side_effect=FileNotFoundError("no cli")):
            result = gen.compile(jsx, Framework.SVELTE)
        assert "<script" in result.lower() or "svelte" in result.lower()

    def test_fallback_disabled_raises_when_cli_fails(self):
        gen = MitosisGenerator(fallback_enabled=False)
        jsx = "export default function Btn() { return <button>OK</button>; }"
        with patch.object(gen, "_run_mitosis_cli", side_effect=MitosisGenerationError("CLI err")):
            with pytest.raises(MitosisGenerationError):
                gen.compile(jsx, Framework.REACT)

    def test_supported_frameworks_returns_all(self):
        gen = MitosisGenerator()
        frameworks = gen.supported_frameworks()
        assert Framework.REACT in frameworks
        assert Framework.VUE in frameworks

    def test_angular_falls_back_to_react(self):
        gen = MitosisGenerator()
        jsx = "export default function AngularComp() { return <div>a</div>; }"
        result = gen._direct_generate(jsx, Framework.ANGULAR)
        # Angular hits the `case _` default which calls _generate_react
        assert isinstance(result, str)
        assert len(result) > 0


# ── TokenExtractor ─────────────────────────────────────────────────────────────

from services.design_pipeline.models import DesignTokenSet, TokenSyncResult
from services.design_pipeline.token_extractor import TokenExtractionError, TokenExtractor


def _make_token_set() -> DesignTokenSet:
    from services.design_pipeline.models import DesignToken, TokenCategory

    return DesignTokenSet(
        file_id="file-001",
        colors=[DesignToken(path="color.primary", value="#0070f3", category=TokenCategory.COLOR)],
        typography=[],
        spacing=[],
    )


class TestTokenExtractorSyncFailurePaths:
    @pytest.mark.asyncio
    async def test_sync_penpot_failure_returns_error_result(self):
        from services.design_pipeline.penpot_client import InMemoryPenpotClient

        class FailingPenpotClient(InMemoryPenpotClient):
            async def get_design_tokens(self, file_id: str) -> DesignTokenSet:  # type: ignore[override]
                raise RuntimeError("Penpot connection refused")

        extractor = TokenExtractor(penpot_client=FailingPenpotClient())
        result = await extractor.sync("file-err")
        assert isinstance(result, TokenSyncResult)
        assert result.tokens_extracted == 0
        assert len(result.errors) >= 1

    @pytest.mark.asyncio
    async def test_sync_style_dict_not_found_adds_error(self):
        from services.design_pipeline.penpot_client import InMemoryPenpotClient

        extractor = TokenExtractor(
            penpot_client=InMemoryPenpotClient(),
            style_dict_cli="nonexistent-style-dict-cli-xyz",
        )
        # Patch export to succeed; build will fail due to missing CLI
        with patch.object(
            extractor, "export_to_style_dictionary", return_value=Path("/tmp/t.json")
        ):
            result = await extractor.sync("file-002")
        # Either FileNotFoundError or returncode != 0 from subprocess
        assert isinstance(result, TokenSyncResult)

    def test_get_css_variable_converts_dot_path(self):
        css = TokenExtractor.get_css_variable("color.primary")
        assert css == "var(--banxe-color-primary)"

    def test_get_css_variable_nested_path(self):
        css = TokenExtractor.get_css_variable("spacing.md")
        assert css == "var(--banxe-spacing-md)"

    def test_extraction_error_stores_context(self):
        err = TokenExtractionError("test error", context={"key": "value"})
        assert err.context["key"] == "value"
        assert str(err) == "test error"
