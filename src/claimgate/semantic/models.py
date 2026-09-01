"""Strict response schemas for untrusted semantic model output."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from claimgate.domain import ClaimCategory


class StrictSemanticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ExtractedClaim(StrictSemanticModel):
    claim_id: str = Field(min_length=1)
    category: ClaimCategory = Field(strict=False)
    normalized_value: str = Field(min_length=1)
    source_text: str = Field(min_length=1)
    critical: bool


class ClaimExtractionPayload(StrictSemanticModel):
    complete: bool
    claims: list[ExtractedClaim]


class SemanticVerificationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONFLICTING = "CONFLICTING"
    UNSUPPORTED = "UNSUPPORTED"
    UNCERTAIN = "UNCERTAIN"


class EvidenceComparison(StrictSemanticModel):
    claim_id: str = Field(min_length=1)
    status: SemanticVerificationStatus = Field(strict=False)
    evidence_id: str | None
    quotation: str | None
    notes: str = Field(min_length=1)


class EvidenceComparisonPayload(StrictSemanticModel):
    complete: bool
    results: list[EvidenceComparison]
