"""Controlled ingestion of plain and already-extracted PDF evidence text."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from claimgate.domain import EvidenceSource
from claimgate.evidence_graph import EvidenceAuthority, EvidenceProvenance
from claimgate.extraction import ExtractedDocument


class EvidenceKind(str, Enum):
    PLAIN_TEXT = "plain_text"
    PDF_DERIVED_TEXT = "pdf_derived_text"
    PUBLIC_SEARCH_SNIPPET = "public_search_snippet"


@dataclass(frozen=True)
class EvidenceDocument:
    source: EvidenceSource
    kind: EvidenceKind
    authority: EvidenceAuthority = EvidenceAuthority.INTERNAL
    provenance: EvidenceProvenance | None = None
    extracted_document: ExtractedDocument | None = None


class EvidenceIngestor:
    """Create immutable policy evidence from text; PDF parsing stays with Foxit."""

    @staticmethod
    def plain_text(
        *,
        source_id: str,
        title: str,
        text: str,
        authority: EvidenceAuthority = EvidenceAuthority.INTERNAL,
    ) -> EvidenceDocument:
        return EvidenceDocument(
            source=EvidenceSource(source_id=source_id, title=title, content=text),
            kind=EvidenceKind.PLAIN_TEXT,
            authority=authority,
        )

    @staticmethod
    def pdf_derived_text(
        *,
        source_id: str,
        title: str,
        extracted_text: str,
        authority: EvidenceAuthority = EvidenceAuthority.INTERNAL,
        extracted_document: ExtractedDocument | None = None,
    ) -> EvidenceDocument:
        return EvidenceDocument(
            source=EvidenceSource(
                source_id=source_id,
                title=title,
                content=extracted_text,
            ),
            kind=EvidenceKind.PDF_DERIVED_TEXT,
            authority=authority,
            extracted_document=extracted_document,
        )
