"""Strict public-evidence discovery and provenance contracts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from claimgate.domain import ClaimCategory, EvidenceSource
from claimgate.evidence_graph import (
    EvidenceAuthority,
    EvidenceProvenance,
    EvidenceSourceType,
)
from claimgate.semantic import EvidenceDocument, EvidenceKind

PUBLIC_EVIDENCE_SNIPPET_MARKER = "\nPUBLIC_EVIDENCE_SNIPPET\n"


class StrictPublicEvidenceModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class PublicFactType(str, Enum):
    PARTY_IDENTITY = "PARTY_IDENTITY"
    CERTIFICATION_STATUS = "CERTIFICATION_STATUS"
    PUBLIC_COMPANY_INFORMATION = "PUBLIC_COMPANY_INFORMATION"
    PRODUCT_SPECIFICATION = "PRODUCT_SPECIFICATION"


class PublicEvidenceQuery(StrictPublicEvidenceModel):
    claim_id: str = Field(min_length=1, max_length=100)
    claim_category: ClaimCategory = Field(strict=False)
    fact_type: PublicFactType = Field(strict=False)
    normalized_claim: str = Field(min_length=1, max_length=300)
    query: str = Field(min_length=1, max_length=320)
    official_domains: tuple[str, ...] = Field(default=(), max_length=5)

    @field_validator("official_domains", mode="before")
    @classmethod
    def normalize_official_domains(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted({str(item).strip().lower() for item in value}))
        return value


class PublicEvidenceCandidate(StrictPublicEvidenceModel):
    source_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(min_length=1, max_length=4000)
    retrieved_at: datetime
    query: str = Field(min_length=1, max_length=320)
    authority: EvidenceAuthority = Field(strict=False)
    provider: str = Field(min_length=1, max_length=80)
    provenance_metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def normalize_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Public evidence retrieval time must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Public evidence URL must be HTTP(S)")
        if parsed.username or parsed.password:
            raise ValueError("Public evidence URL cannot contain credentials")
        return value

    @model_validator(mode="after")
    def candidate_is_never_internal(self) -> PublicEvidenceCandidate:
        if self.authority in {
            EvidenceAuthority.AUTHORITATIVE_INTERNAL,
            EvidenceAuthority.INTERNAL,
        }:
            raise ValueError("Public search cannot create internal evidence authority")
        hostname = (urlsplit(self.url).hostname or "").lower()
        if hostname != self.domain.lower():
            raise ValueError("Public evidence domain must match its URL")
        return self


class PublicEvidenceProviderResponse(StrictPublicEvidenceModel):
    provider: str = Field(min_length=1, max_length=80)
    candidates: tuple[PublicEvidenceCandidate, ...] = Field(max_length=10)

    @field_validator("candidates", mode="before")
    @classmethod
    def accept_json_array(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value


class PublicEvidenceSource(StrictPublicEvidenceModel):
    source_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=300)
    url: str = Field(min_length=8, max_length=2000)
    canonical_url: str = Field(min_length=8, max_length=2000)
    domain: str = Field(min_length=1, max_length=253)
    snippet: str = Field(min_length=1, max_length=4000)
    retrieved_at: datetime
    query: str = Field(min_length=1, max_length=320)
    authority: EvidenceAuthority = Field(strict=False)
    source_type: EvidenceSourceType = Field(strict=False)
    provider: str = Field(min_length=1, max_length=80)
    provenance_metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def normalize_source_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Public evidence retrieval time must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def source_is_never_internal(self) -> PublicEvidenceSource:
        if self.authority in {
            EvidenceAuthority.AUTHORITATIVE_INTERNAL,
            EvidenceAuthority.INTERNAL,
        }:
            raise ValueError("Public evidence can never be internal authority")
        return self

    def to_evidence_document(self) -> EvidenceDocument:
        provenance_envelope = json.dumps(
            {
                "authority": self.authority.value,
                "domain": self.domain,
                "provider": self.provider,
                "query": self.query,
                "retrieved_at": self.retrieved_at.isoformat(),
                "source_type": self.source_type.value,
                "source_url": self.canonical_url,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return EvidenceDocument(
            source=EvidenceSource(
                source_id=self.source_id,
                title=self.title,
                content=(
                    "PUBLIC_EVIDENCE_PROVENANCE "
                    + provenance_envelope
                    + PUBLIC_EVIDENCE_SNIPPET_MARKER
                    + self.snippet
                ),
            ),
            kind=EvidenceKind.PUBLIC_SEARCH_SNIPPET,
            authority=self.authority,
            provenance=EvidenceProvenance(
                provider=self.provider,
                source_url=self.canonical_url,
                domain=self.domain,
                retrieved_at=self.retrieved_at,
                query=self.query,
                source_type=self.source_type,
            ),
        )


class PublicEvidenceDiscoveryResult(StrictPublicEvidenceModel):
    query: PublicEvidenceQuery | None
    provider: str
    eligible: bool
    searched: bool
    succeeded: bool
    sources: tuple[PublicEvidenceSource, ...]
    blocker_codes: tuple[str, ...] = ()
    message: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def outcome_is_consistent(self) -> PublicEvidenceDiscoveryResult:
        if self.succeeded and (not self.eligible or not self.searched):
            raise ValueError("Successful discovery must be eligible and searched")
        if not self.succeeded and not self.blocker_codes:
            raise ValueError("Failed discovery requires a blocker code")
        return self
