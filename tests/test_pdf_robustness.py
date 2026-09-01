from __future__ import annotations

from pathlib import Path

import pytest

from claimgate.application import Phase3Workflow
from claimgate.domain import PolicyOutcome, WorkflowState
from claimgate.evidence_graph import EvidenceAuthority
from claimgate.extraction import (
    ExtractionBlockerCode,
    ExtractionQualityStatus,
    build_extracted_document,
    chunk_document,
    detect_material_ambiguities,
)
from claimgate.semantic import (
    EvidenceIngestor,
    ScriptedSemanticProvider,
    SemanticEngine,
)


def _pdf(path: Path, pages: int) -> Path:
    path.write_bytes(b"%PDF-1.7\n" + b"\n".join(b"<< /Type /Page >>" for _ in range(pages)))
    return path


def _page(content: str) -> str:
    return content + "\n" + (f"ordinary obligation context for {content} " * 5)


class TextAdapter:
    def __init__(self, text: str, *, used_ocr: bool = False) -> None:
        self.text = text
        self.used_ocr = used_ocr

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        return _pdf(output_path, max(1, self.text.count("\f") + 1))

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        output_path.write_text(self.text)
        return self.text

    def extraction_used_ocr(self, output_path: Path) -> bool:
        return self.used_ocr


def test_five_page_document_is_chunked_without_splitting_pages(tmp_path: Path) -> None:
    text = "\f".join(_page(f"Page {number}") for number in range(1, 6))
    document = build_extracted_document(text, pdf_path=_pdf(tmp_path / "five.pdf", 5))

    chunks = chunk_document(document)

    assert [(chunk.page_start, chunk.page_end) for chunk in chunks] == [(1, 3), (4, 5)]
    assert [chunk.chunk_id for chunk in chunks] == ["chunk-001", "chunk-002"]
    assert document.quality.status is ExtractionQualityStatus.GOOD
    assert document.page_provenance_available is True


def test_flat_long_output_uses_stable_section_chunks(tmp_path: Path) -> None:
    sections = [
        f"Obligation section {number}\n" + (f"term-{number} " * 40) for number in range(1, 7)
    ]
    document = build_extracted_document(
        "\n\n".join(sections),
        pdf_path=_pdf(tmp_path / "flat-long.pdf", 5),
    )

    chunks = chunk_document(document, max_characters=900)

    assert len(chunks) >= 3
    assert all(len(chunk.text) <= 900 for chunk in chunks)
    assert document.page_provenance_available is False


def test_flat_long_output_without_boundaries_refuses_unsafe_chunking(tmp_path: Path) -> None:
    document = build_extracted_document(
        "Obligation:" + ("x" * 13_000),
        pdf_path=_pdf(tmp_path / "unbounded.pdf", 5),
    )

    with pytest.raises(ValueError, match="no stable section boundary"):
        chunk_document(document)


@pytest.mark.asyncio
async def test_later_page_material_claim_keeps_page_provenance(tmp_path: Path) -> None:
    material = "Contract amount: USD 12,500"
    text = "\f".join(
        _page(material if page_number == 4 else f"Standard terms page {page_number}")
        for page_number in range(1, 6)
    )

    def extract(request):
        page_text = "\n".join(page["text"] for page in request.untrusted_data["pages"])
        claims = []
        if material in page_text:
            claims.append(
                {
                    "claim_id": "money",
                    "category": "money",
                    "normalized_value": "USD 12500",
                    "source_text": material,
                    "critical": True,
                }
            )
        return {"complete": True, "claims": claims}

    provider = ScriptedSemanticProvider([extract, extract])
    engine = SemanticEngine(provider)
    document = build_extracted_document(text, pdf_path=_pdf(tmp_path / "later.pdf", 5))

    result = await engine.extract_claims_page_aware(document)

    assert result.chunk_count == 2
    assert result.claims[0].claim_id == "money"
    assert result.provenance[0].page_numbers == (4,)
    assert result.provenance[0].chunk_id == "chunk-002"


@pytest.mark.asyncio
async def test_chunk_merge_retains_conflicting_values(tmp_path: Path) -> None:
    first = "Contract amount: USD 12,500"
    second = "Contract amount: USD 15,000"
    text = "\f".join(
        _page(first if number == 1 else second if number == 4 else f"Clause {number}")
        for number in range(1, 5)
    )

    def extract(request):
        page_text = "\n".join(page["text"] for page in request.untrusted_data["pages"])
        claims = []
        for source, normalized in ((first, "USD 12500"), (second, "USD 15000")):
            if source in page_text:
                claims.append(
                    {
                        "claim_id": "money",
                        "category": "money",
                        "normalized_value": normalized,
                        "source_text": source,
                        "critical": True,
                    }
                )
        return {"complete": True, "claims": claims}

    document = build_extracted_document(text, pdf_path=_pdf(tmp_path / "conflict.pdf", 4))
    result = await SemanticEngine(
        ScriptedSemanticProvider([extract, extract])
    ).extract_claims_page_aware(document)

    assert [claim.normalized_value for claim in result.claims] == ["USD 12500", "USD 15000"]
    assert [claim.claim_id for claim in result.claims] == ["money", "chunk-002:money"]
    assert detect_material_ambiguities(document)[0].code == "AMBIGUOUS_MONEY_VALUE"


def test_table_noise_is_degraded_but_not_reinterpreted(tmp_path: Path) -> None:
    text = _page("Item | Quantity | Delivery\nDevices | 250 | 2026-09-30\nSupport | Included")

    document = build_extracted_document(text, pdf_path=_pdf(tmp_path / "table.pdf", 1))

    assert document.quality.status is ExtractionQualityStatus.DEGRADED
    assert document.quality.table_detected is True
    assert "EXTRACTION_TABLE_STRUCTURE_DEGRADED" in {
        check.code for check in document.quality.checks
    }


@pytest.mark.asyncio
async def test_scanned_like_extraction_fails_closed_before_semantics(tmp_path: Path) -> None:
    provider = ScriptedSemanticProvider([])
    evidence = EvidenceIngestor.plain_text(
        source_id="authority",
        title="Authority",
        text="Approved amount is USD 12,500.",
    )
    uploaded = _pdf(tmp_path / "scan.pdf", 4)

    result = await Phase3Workflow(TextAdapter("  \n"), SemanticEngine(provider)).run_from_document(
        run_id="scanned-like",
        pdf_path=uploaded,
        evidence_documents=(evidence,),
        output_path=tmp_path / "scan-copy.pdf",
    )

    assert provider.requests == []
    assert result.workflow.state is WorkflowState.BLOCKED
    assert result.decision.outcome is PolicyOutcome.BLOCKED
    assert result.extracted_document.quality.status is ExtractionQualityStatus.INSUFFICIENT
    assert ExtractionBlockerCode.OCR_REQUIRED.value in (
        result.extracted_document.quality.blocker_codes
    )
    assert "VERIFICATION_FAILED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.asyncio
async def test_multiple_money_candidates_become_uncertain_and_block(tmp_path: Path) -> None:
    first = "Contract amount: USD 12,500"
    second = "Alternate contract amount: USD 15,000"
    text = _page(f"{first}\n{second}")
    extraction = {
        "complete": True,
        "claims": [
            {
                "claim_id": "money",
                "category": "money",
                "normalized_value": "USD 12500",
                "source_text": first,
                "critical": True,
            }
        ],
    }
    comparison = {
        "complete": True,
        "results": [
            {
                "claim_id": "money",
                "status": "SUPPORTED",
                "evidence_id": "authority",
                "quotation": "Approved amount: USD 12,500",
                "notes": "Exact evidence match",
            }
        ],
    }
    evidence = EvidenceIngestor.plain_text(
        source_id="authority",
        title="Authority",
        text="Approved amount: USD 12,500",
    )

    result = await Phase3Workflow(
        TextAdapter(text),
        SemanticEngine(ScriptedSemanticProvider([extraction, comparison])),
    ).run_from_document(
        run_id="ambiguous-money",
        pdf_path=_pdf(tmp_path / "ambiguous.pdf", 1),
        evidence_documents=(evidence,),
        output_path=tmp_path / "ambiguous-copy.pdf",
    )

    assert result.verification.results[0].status.value == "UNCERTAIN"
    assert result.workflow.state is WorkflowState.BLOCKED
    assert result.extraction_ambiguities[0].code == "AMBIGUOUS_MONEY_VALUE"
    assert "CRITICAL_CLAIM_UNCERTAIN" in {blocker.code for blocker in result.decision.blockers}


def test_repeated_headers_are_reported_as_degraded(tmp_path: Path) -> None:
    pages = [
        _page(f"CLAIMGATE MASTER AGREEMENT\nUnique clause for page {number}")
        for number in range(1, 5)
    ]
    document = build_extracted_document(
        "\f".join(pages), pdf_path=_pdf(tmp_path / "headers.pdf", 4)
    )

    assert document.quality.status is ExtractionQualityStatus.DEGRADED
    assert "EXTRACTION_REPEATED_PAGE_NOISE" in {check.code for check in document.quality.checks}


def test_ocr_output_does_not_gain_authoritative_evidence_status(tmp_path: Path) -> None:
    text = _page("Approved amount: USD 12,500")
    extracted_document = build_extracted_document(
        text,
        pdf_path=_pdf(tmp_path / "ocr.pdf", 1),
        used_ocr=True,
    )

    evidence = EvidenceIngestor.pdf_derived_text(
        source_id="ocr-evidence",
        title="OCR evidence",
        extracted_text=text,
        extracted_document=extracted_document,
    )

    assert evidence.authority is EvidenceAuthority.INTERNAL
    assert evidence.extracted_document is not None
    assert evidence.extracted_document.quality.used_ocr is True
