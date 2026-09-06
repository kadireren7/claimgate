"""Conservative PDF extraction quality, provenance, and chunking primitives."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class ExtractionQualityStatus(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"


class ExtractionBlockerCode(str, Enum):
    EXTRACTION_EMPTY = "EXTRACTION_EMPTY"
    EXTRACTION_LOW_TEXT_DENSITY = "EXTRACTION_LOW_TEXT_DENSITY"
    EXTRACTION_GARBLED = "EXTRACTION_GARBLED"
    EXTRACTION_INCOMPLETE = "EXTRACTION_INCOMPLETE"
    OCR_REQUIRED = "OCR_REQUIRED"
    AMBIGUOUS_MONEY_VALUE = "AMBIGUOUS_MONEY_VALUE"
    AMBIGUOUS_DATE_VALUE = "AMBIGUOUS_DATE_VALUE"
    AMBIGUOUS_QUANTITY_VALUE = "AMBIGUOUS_QUANTITY_VALUE"
    AMBIGUOUS_PARTY_VALUE = "AMBIGUOUS_PARTY_VALUE"


@dataclass(frozen=True)
class ExtractionQualityCheck:
    code: str
    status: ExtractionQualityStatus
    message: str
    page_number: int | None = None


@dataclass(frozen=True)
class PageText:
    page_number: int
    text: str
    quality_status: ExtractionQualityStatus
    table_like: bool = False


@dataclass(frozen=True)
class ExtractionQuality:
    status: ExtractionQualityStatus
    checks: tuple[ExtractionQualityCheck, ...]
    page_count: int
    pages_with_text: int
    coverage_ratio: float
    printable_ratio: float
    garbled_ratio: float
    text_characters: int
    table_detected: bool
    used_ocr: bool = False

    @property
    def blocker_codes(self) -> tuple[str, ...]:
        return tuple(
            check.code
            for check in self.checks
            if check.status is ExtractionQualityStatus.INSUFFICIENT
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(
            check.message
            for check in self.checks
            if check.status is not ExtractionQualityStatus.GOOD
        )


@dataclass(frozen=True)
class ExtractedDocument:
    pages: tuple[PageText, ...]
    combined_text: str
    quality: ExtractionQuality
    page_provenance_available: bool


@dataclass(frozen=True)
class DocumentChunk:
    chunk_id: str
    page_start: int
    page_end: int
    pages: tuple[PageText, ...]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages)


@dataclass(frozen=True)
class ClaimProvenance:
    claim_id: str
    page_numbers: tuple[int, ...]
    chunk_id: str
    table_origin: bool


@dataclass(frozen=True)
class ExtractionAmbiguity:
    code: str
    category: str
    candidates: tuple[str, ...]
    page_numbers: tuple[int, ...]
    message: str


_PAGE_MARKER = re.compile(r"(?im)^\s*(?:---\s*)?page\s+(\d+)\s*(?:---)?\s*$")
_PDF_PAGE = re.compile(rb"/Type\s*/Page(?!s)\b")
_MONEY = re.compile(
    r"(?i)(?:USD|EUR|GBP|TRY|\$|€|£|₺)\s*[\d][\d,.]*|[\d][\d,.]*\s*(?:USD|EUR|GBP|TRY)"
)
_DATE = re.compile(r"\b(?:20\d{2}[-/.](?:0?[1-9]|1[0-2])[-/.](?:0?[1-9]|[12]\d|3[01]))\b")
_QUANTITY = re.compile(r"(?i)\b(?:quantity|qty|units?)\s*[:=-]?\s*(\d[\d,]*)\b")
_PARTY = re.compile(
    r"(?im)^\s*(?:party(?: name)?|counterparty|supplier|customer)\s*[:=-]\s*(.{2,120})$"
)
_MATERIAL_FIELD = re.compile(
    r"(?i)\b(?:party|counterparty|supplier|customer|amount|price|total|quantity|qty|"
    r"delivery|effective date|scope|deliverable|obligation)\b"
)


def estimate_pdf_page_count(pdf_path: Path) -> int:
    """Best-effort local count used only for quality checks, never authorization."""

    try:
        count = len(_PDF_PAGE.findall(pdf_path.read_bytes()))
    except OSError:
        return 1
    return max(1, count)


def build_extracted_document(
    text: str,
    *,
    pdf_path: Path,
    used_ocr: bool = False,
) -> ExtractedDocument:
    estimated_pages = estimate_pdf_page_count(pdf_path)
    page_parts, provenance_available = _split_pages(text, estimated_pages)
    page_count = max(estimated_pages, len(page_parts))
    if provenance_available and len(page_parts) < page_count:
        page_parts.extend("" for _ in range(page_count - len(page_parts)))

    printable = sum(character.isprintable() or character in "\n\r\t" for character in text)
    total = max(1, len(text))
    printable_ratio = printable / total
    garbled = sum(
        character == "\ufffd"
        or (unicodedata.category(character) == "Cc" and character not in "\n\r\t\f")
        for character in text
    )
    garbled_ratio = garbled / total
    non_whitespace = sum(not character.isspace() for character in text)
    observed_pages_with_text = sum(bool(page.strip()) for page in page_parts)
    pages_with_text = (
        observed_pages_with_text if provenance_available else page_count if text.strip() else 0
    )
    coverage = pages_with_text / page_count
    density = non_whitespace / page_count
    checks: list[ExtractionQualityCheck] = []

    if not text.strip():
        checks.append(
            _insufficient(
                ExtractionBlockerCode.EXTRACTION_EMPTY, "Foxit returned no extractable text."
            )
        )
        checks.append(
            _insufficient(
                ExtractionBlockerCode.OCR_REQUIRED,
                "This PDF appears image-based; OCR is required before safe verification.",
            )
        )
    elif density < 40:
        checks.append(
            _insufficient(
                ExtractionBlockerCode.EXTRACTION_LOW_TEXT_DENSITY,
                "Extracted text density is too low for safe verification.",
            )
        )
        checks.append(
            _insufficient(
                ExtractionBlockerCode.OCR_REQUIRED,
                "This PDF appears image-based; OCR is required before safe verification.",
            )
        )
    elif density < 120:
        checks.append(
            _degraded(
                ExtractionBlockerCode.EXTRACTION_LOW_TEXT_DENSITY,
                "Text density is low; review source citations carefully.",
            )
        )

    if printable_ratio < 0.85 or garbled_ratio > 0.08:
        checks.append(
            _insufficient(
                ExtractionBlockerCode.EXTRACTION_GARBLED,
                "Extracted text contains too many unreadable characters.",
            )
        )
    elif printable_ratio < 0.96 or garbled_ratio > 0.02:
        checks.append(
            _degraded(
                ExtractionBlockerCode.EXTRACTION_GARBLED,
                "Some extracted characters may be unreadable.",
            )
        )

    if coverage < 0.5:
        checks.append(
            _insufficient(
                ExtractionBlockerCode.EXTRACTION_INCOMPLETE,
                "Text was extracted from fewer than half of the detected pages.",
            )
        )
    elif coverage < 1:
        checks.append(
            _degraded(
                ExtractionBlockerCode.EXTRACTION_INCOMPLETE,
                "One or more detected pages have no extracted text.",
            )
        )

    repeated_ratio = _repeated_line_ratio(page_parts)
    if repeated_ratio > 0.25:
        checks.append(
            _degraded(
                "EXTRACTION_REPEATED_PAGE_NOISE",
                "Repeated headers or footers may reduce extraction clarity.",
            )
        )

    if text.strip() and not _MATERIAL_FIELD.search(text):
        checks.append(
            _degraded(
                ExtractionBlockerCode.EXTRACTION_INCOMPLETE,
                "No known material-field labels were detected; semantic coverage must be reviewed.",
            )
        )

    table_flags = tuple(_is_table_like(page) for page in page_parts)
    if any(table_flags) and any(_ambiguous_table(page) for page in page_parts):
        checks.append(
            _degraded(
                "EXTRACTION_TABLE_STRUCTURE_DEGRADED",
                "Table-like content was found, but row or column structure is inconsistent.",
            )
        )

    status = ExtractionQualityStatus.GOOD
    if any(check.status is ExtractionQualityStatus.INSUFFICIENT for check in checks):
        status = ExtractionQualityStatus.INSUFFICIENT
    elif checks:
        status = ExtractionQualityStatus.DEGRADED
    pages = tuple(
        PageText(
            page_number=index + 1,
            text=page,
            quality_status=_page_status(page),
            table_like=table_flags[index],
        )
        for index, page in enumerate(page_parts)
    )
    return ExtractedDocument(
        pages=pages,
        combined_text=text,
        quality=ExtractionQuality(
            status=status,
            checks=tuple(checks),
            page_count=page_count,
            pages_with_text=pages_with_text,
            coverage_ratio=coverage,
            printable_ratio=printable_ratio,
            garbled_ratio=garbled_ratio,
            text_characters=len(text),
            table_detected=any(table_flags),
            used_ocr=used_ocr,
        ),
        page_provenance_available=provenance_available,
    )


def chunk_document(
    document: ExtractedDocument,
    *,
    max_pages: int = 3,
    max_characters: int = 12_000,
) -> tuple[DocumentChunk, ...]:
    """Create deterministic whole-page chunks; pages are never split."""

    source_pages = document.pages
    if (
        not document.page_provenance_available
        and len(source_pages) == 1
        and len(source_pages[0].text) > max_characters
    ):
        source_pages = _stable_section_pages(source_pages[0], max_characters)

    chunks: list[DocumentChunk] = []
    pending: list[PageText] = []
    pending_chars = 0
    for page in source_pages:
        would_overflow = pending and (
            len(pending) >= max_pages or pending_chars + len(page.text) > max_characters
        )
        if would_overflow:
            chunks.append(_make_chunk(len(chunks) + 1, pending))
            pending = []
            pending_chars = 0
        pending.append(page)
        pending_chars += len(page.text)
    if pending:
        chunks.append(_make_chunk(len(chunks) + 1, pending))
    return tuple(chunks)


def _stable_section_pages(page: PageText, max_characters: int) -> tuple[PageText, ...]:
    """Bound flat Foxit output by paragraph/line boundaries without inventing pages."""

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", page.text) if part.strip()]
    if len(paragraphs) == 1:
        paragraphs = [line.strip() for line in page.text.splitlines() if line.strip()]
    if any(len(part) > max_characters for part in paragraphs):
        raise ValueError(
            "Long extracted text has no stable section boundary; safe chunking is unavailable"
        )
    sections: list[str] = []
    pending: list[str] = []
    pending_size = 0
    for paragraph in paragraphs:
        added_size = len(paragraph) + (2 if pending else 0)
        if pending and pending_size + added_size > max_characters:
            sections.append("\n\n".join(pending))
            pending = []
            pending_size = 0
        pending.append(paragraph)
        pending_size += len(paragraph) + (2 if len(pending) > 1 else 0)
    if pending:
        sections.append("\n\n".join(pending))
    return tuple(
        PageText(
            page_number=page.page_number,
            text=section,
            quality_status=page.quality_status,
            table_like=_is_table_like(section),
        )
        for section in sections
    )


def locate_claim_source(document: ExtractedDocument, source_text: str) -> tuple[int, ...]:
    return tuple(page.page_number for page in document.pages if source_text in page.text)


def detect_material_ambiguities(document: ExtractedDocument) -> tuple[ExtractionAmbiguity, ...]:
    patterns = (
        (ExtractionBlockerCode.AMBIGUOUS_MONEY_VALUE, "money", _MONEY),
        (ExtractionBlockerCode.AMBIGUOUS_DATE_VALUE, "dates", _DATE),
        (ExtractionBlockerCode.AMBIGUOUS_QUANTITY_VALUE, "quantity", _QUANTITY),
        (ExtractionBlockerCode.AMBIGUOUS_PARTY_VALUE, "party_identity", _PARTY),
    )
    ambiguities: list[ExtractionAmbiguity] = []
    for code, category, pattern in patterns:
        candidates_by_field: dict[str, dict[str, set[int]]] = {}
        for page in document.pages:
            for match in pattern.finditer(page.text):
                raw = match.group(1) if match.lastindex else match.group(0)
                normalized = " ".join(raw.casefold().replace(",", "").split())
                field = (
                    _money_semantic_field(page.text, match.start())
                    if category == "money"
                    else category
                )
                candidates_by_field.setdefault(field, {}).setdefault(normalized, set()).add(
                    page.page_number
                )
        ambiguous_groups = [
            candidates for candidates in candidates_by_field.values() if len(candidates) > 1
        ]
        if ambiguous_groups:
            candidates = {
                value: pages
                for group in ambiguous_groups
                for value, pages in group.items()
            }
            pages = (
                sorted({number for numbers in candidates.values() for number in numbers})
                if document.page_provenance_available
                else []
            )
            ambiguities.append(
                ExtractionAmbiguity(
                    code=code.value,
                    category=category,
                    candidates=tuple(sorted(candidates)),
                    page_numbers=tuple(pages),
                    message=(
                        f"Multiple candidate {category.replace('_', ' ')} values "
                        "require explicit resolution."
                    ),
                )
            )
    return tuple(ambiguities)


def _money_semantic_field(text: str, match_start: int) -> str:
    """Separate clearly labeled totals from unit prices before ambiguity gating."""

    line_start = text.rfind("\n", 0, match_start) + 1
    previous_start = text.rfind("\n", 0, max(0, line_start - 1)) + 1
    line_end = text.find("\n", match_start)
    if line_end < 0:
        line_end = len(text)
    context = text[previous_start:line_end].casefold()
    if "contract amount" in context or "total amount payable" in context:
        return "contract_total"
    if "unit price" in context or re.search(r"\bunits?\b", context):
        return "unit_price"
    return "unlabeled_money"


def _split_pages(text: str, estimated_pages: int) -> tuple[list[str], bool]:
    if "\f" in text:
        return [part.strip() for part in text.split("\f")], True
    markers = list(_PAGE_MARKER.finditer(text))
    if markers:
        parts: list[str] = []
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
            parts.append(text[start:end].strip())
        return parts, True
    return [text.strip()], estimated_pages == 1


def _repeated_line_ratio(pages: list[str]) -> float:
    if len(pages) < 2:
        return 0.0
    lines = [
        line.strip().casefold()
        for page in pages
        for line in page.splitlines()
        if len(line.strip()) >= 4
    ]
    if not lines:
        return 0.0
    counts = Counter(lines)
    repeated = sum(count for count in counts.values() if count >= 2)
    return repeated / len(lines)


def _is_table_like(text: str) -> bool:
    rows = [line for line in text.splitlines() if line.strip()]
    table_rows = sum(
        "|" in row or "\t" in row or bool(re.search(r"\S\s{2,}\S", row)) for row in rows
    )
    return table_rows >= 2


def _ambiguous_table(text: str) -> bool:
    counts = [
        len(re.split(r"\s*\|\s*|\t+|\s{2,}", row.strip()))
        for row in text.splitlines()
        if "|" in row or "\t" in row or re.search(r"\S\s{2,}\S", row)
    ]
    return len(counts) >= 2 and len(set(counts)) > 1


def _page_status(text: str) -> ExtractionQualityStatus:
    density = sum(not character.isspace() for character in text)
    if density < 40:
        return ExtractionQualityStatus.INSUFFICIENT
    if density < 120:
        return ExtractionQualityStatus.DEGRADED
    return ExtractionQualityStatus.GOOD


def _make_chunk(index: int, pages: list[PageText]) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=f"chunk-{index:03d}",
        page_start=pages[0].page_number,
        page_end=pages[-1].page_number,
        pages=tuple(pages),
    )


def _degraded(code: ExtractionBlockerCode | str, message: str) -> ExtractionQualityCheck:
    return ExtractionQualityCheck(
        code=code.value if isinstance(code, ExtractionBlockerCode) else code,
        status=ExtractionQualityStatus.DEGRADED,
        message=message,
    )


def _insufficient(code: ExtractionBlockerCode, message: str) -> ExtractionQualityCheck:
    return ExtractionQualityCheck(
        code=code.value, status=ExtractionQualityStatus.INSUFFICIENT, message=message
    )
