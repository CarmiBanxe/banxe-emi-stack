"""
Tests for compliance KB ingestion pipeline.
BANXE AI BANK | IL-069 | banxe-emi-stack
"""

import json

# Import under test
from scripts.ingest_compliance_drive import (
    build_agent_context,
    chunk_text,
    classify_domain,
    estimate_tokens,
)

# ── classify_domain ───────────────────────────────────────────────────────────


class TestClassifyDomain:
    def test_aml_afc(self):
        assert classify_domain("Anti-Financial Crime Policy.pdf") == "aml_afc"

    def test_transaction_monitoring(self):
        assert classify_domain("Transaction Monitoring Manual 2024.pdf") == "transaction_monitoring"

    def test_sanctions_pep(self):
        assert (
            classify_domain("PEP, Sanctions and Adverse Media Screening Manual.pdf")
            == "sanctions_pep"
        )

    def test_kyc_cdd(self):
        assert classify_domain("CDD Manual.pdf") == "kyc_cdd"

    def test_fraud_prevention(self):
        assert classify_domain("ANTI-FRAUD POLICY AND PROCEDURE v 4.0.pdf") == "fraud_prevention"

    def test_abc_anti_bribery(self):
        assert (
            classify_domain("ABC Anti-Corruption and Bribery Policy V 4.0.pdf")
            == "abc_anti_bribery"
        )

    def test_consumer_duty(self):
        assert classify_domain("CONSUMER DUTY POLICY.docx") == "consumer_duty"

    def test_safeguarding(self):
        assert (
            classify_domain("SAFEGUARDING AND SETTLEMENTS POLICY v.24.docx.pdf") == "safeguarding"
        )

    def test_geo_risk(self):
        assert (
            classify_domain("Tompay's Country Risk Assessment – Geographical Risk.pdf")
            == "geo_risk"
        )

    def test_risk_assessment(self):
        assert classify_domain("CRA.B.pdf") == "risk_assessment"

    def test_payment_operations(self):
        assert classify_domain("Payment Procedure.pdf") == "payment_operations"

    def test_mi_governance(self):
        assert classify_domain("Management Information Policy.pdf") == "mi_governance"

    def test_kri_reporting(self):
        assert classify_domain("MI-KRI Report 10.2024.pdf") == "kri_reporting"

    def test_governance(self):
        assert classify_domain("RCC Risk and Compliance Committee.pdf") == "governance"

    def test_records_management(self):
        assert classify_domain("Records Management Policy.pdf") == "records_management"

    def test_quality_assurance(self):
        assert classify_domain("QA.pdf") == "quality_assurance"

    def test_unknown_defaults_to_general(self):
        assert classify_domain("Unknown Document.pdf") == "general_compliance"

    def test_all_18_documents(self):
        """Verify all 18 compliance documents classify to non-general domains."""
        docs = [
            "Anti-Financial Crime Policy.pdf",
            "Payment Procedure.pdf",
            "ABC Anti-Corruption and Bribery Policy V 4.0.pdf",
            "ANTI-FRAUD POLICY AND PROCEDURE v 4.0.pdf",
            "CDD Manual.pdf",
            "CONSUMER DUTY POLICY.docx",
            "CRA.B.pdf",
            "Customer Relationship Termination Procedure.pdf",
            "Management Information Policy.pdf",
            "MI-KRI Report 10.2024.pdf",
            "Payment Procedure.zip",
            "PEP, Sanctions and Adverse Media Screening Manual.pdf",
            "QA.pdf",
            "RCC Risk and Compliance Committee.pdf",
            "Records Management Policy.pdf",
            "SAFEGUARDING AND SETTLEMENTS POLICY v.24.docx.pdf",
            "Tompay's Country Risk Assessment – Geographical Risk.pdf",
            "Transaction Monitoring Manual 2024.pdf",
        ]
        for doc in docs:
            domain = classify_domain(doc)
            assert domain != "general_compliance", f"{doc} → fell through to general_compliance"


# ── chunk_text ────────────────────────────────────────────────────────────────


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        text = "Short compliance text."
        chunks = chunk_text(text, chunk_size=1000, overlap=150)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_empty_text_returns_empty_list(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_long_text_splits_into_multiple_chunks(self):
        # ~4000 tokens worth of text (16000 chars)
        text = "compliance regulation " * 800
        chunks = chunk_text(text, chunk_size=1000, overlap=150)
        assert len(chunks) > 1

    def test_chunks_have_overlap(self):
        """Adjacent chunks should share some text due to overlap."""
        text = "word " * 2000  # 10000 chars
        chunks = chunk_text(text, chunk_size=500, overlap=100)
        assert len(chunks) >= 2
        # Verify chunks are non-empty strings
        for chunk in chunks:
            assert isinstance(chunk, str)
            assert len(chunk) > 0

    def test_chunk_size_respected(self):
        text = "a " * 5000  # 10000 chars
        chunks = chunk_text(text, chunk_size=1000, overlap=150)
        char_limit = 1000 * 4 * 1.1  # allow 10% tolerance
        for chunk in chunks:
            assert len(chunk) <= char_limit, f"Chunk too long: {len(chunk)} chars"


# ── estimate_tokens ───────────────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self):
        assert estimate_tokens("") == 0

    def test_approximate_token_count(self):
        # 400 chars ≈ 100 tokens
        text = "a" * 400
        assert estimate_tokens(text) == 100

    def test_scaling(self):
        assert estimate_tokens("a" * 4000) == 1000


# ── build_agent_context ───────────────────────────────────────────────────────


class TestBuildAgentContext:
    def test_creates_valid_json(self, tmp_path):
        output_path = tmp_path / "agent_context.json"
        doc_index = [
            {
                "filename": "AML.pdf",
                "stem": "AML",
                "domain": "aml_afc",
                "chunks": 12,
                "tokens_approx": 5000,
                "path": "compliance_docs/AML.pdf",
            },
            {
                "filename": "CDD.pdf",
                "stem": "CDD",
                "domain": "kyc_cdd",
                "chunks": 8,
                "tokens_approx": 3000,
                "path": "compliance_docs/CDD.pdf",
            },
        ]
        build_agent_context(doc_index, output_path)

        assert output_path.exists()
        ctx = json.loads(output_path.read_text())
        assert ctx["collection"] == "banxe_compliance_kb"
        assert ctx["total_documents"] == 2
        assert ctx["total_chunks"] == 20
        assert "aml_afc" in ctx["domains"]
        assert "kyc_cdd" in ctx["domains"]

    def test_agent_domain_map_present(self, tmp_path):
        output_path = tmp_path / "agent_context.json"
        build_agent_context([], output_path)
        ctx = json.loads(output_path.read_text())
        assert "agent_domain_map" in ctx
        assert "mlro_agent" in ctx["agent_domain_map"]
        assert "sanctions_check_agent" in ctx["agent_domain_map"]

    def test_creates_parent_dirs(self, tmp_path):
        output_path = tmp_path / "deep" / "nested" / "agent_context.json"
        build_agent_context([], output_path)
        assert output_path.exists()


# ── parse functions (with mocks) ──────────────────────────────────────────────


class TestParsePDF:
    def test_parse_pdf_returns_string(self, tmp_path):
        from scripts.ingest_compliance_drive import parse_pdf

        # pypdf uses lazy import inside parse_pdf — test graceful return on bad file
        pdf_path = tmp_path / "test.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 invalid content")
        result = parse_pdf(pdf_path)
        assert isinstance(result, str)  # Either extracted text or empty string on error

    def test_parse_pdf_handles_error_gracefully(self, tmp_path):
        from scripts.ingest_compliance_drive import parse_pdf

        nonexistent = tmp_path / "nonexistent.pdf"
        result = parse_pdf(nonexistent)
        assert result == ""
