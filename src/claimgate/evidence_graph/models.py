"""Typed, deterministic evidence graph models for audit explanations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from claimgate.domain import ClaimCategory


class EvidenceRelationship(str, Enum):
    SUPPORTS = "SUPPORTS"
    CONFLICTS = "CONFLICTS"
    UNCERTAIN = "UNCERTAIN"


class EvidenceAuthority(str, Enum):
    AUTHORITATIVE_INTERNAL = "AUTHORITATIVE_INTERNAL"
    INTERNAL = "INTERNAL"
    VERIFIED_EXTERNAL = "VERIFIED_EXTERNAL"
    UNVERIFIED_EXTERNAL = "UNVERIFIED_EXTERNAL"

    @property
    def is_authoritative(self) -> bool:
        """Authority is display metadata and never a policy input."""

        return self is EvidenceAuthority.AUTHORITATIVE_INTERNAL


class EvidenceSourceType(str, Enum):
    OFFICIAL_ORGANIZATION_DOMAIN = "OFFICIAL_ORGANIZATION_DOMAIN"
    GOVERNMENT_REGULATOR = "GOVERNMENT_REGULATOR"
    CERTIFICATION_REGISTRY = "CERTIFICATION_REGISTRY"
    ESTABLISHED_THIRD_PARTY = "ESTABLISHED_THIRD_PARTY"
    UNKNOWN_THIRD_PARTY = "UNKNOWN_THIRD_PARTY"


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class EvidenceProvenance:
    provider: str
    source_url: str
    domain: str
    retrieved_at: datetime
    query: str
    source_type: EvidenceSourceType

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.provider, "provenance provider"),
            (self.source_url, "provenance source URL"),
            (self.domain, "provenance domain"),
            (self.query, "provenance query"),
        ):
            _require_text(value, field_name)
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("provenance retrieval time must be timezone-aware")
        object.__setattr__(
            self, "retrieved_at", self.retrieved_at.astimezone(timezone.utc)
        )


@dataclass(frozen=True)
class ClaimNode:
    claim_id: str
    category: ClaimCategory
    normalized_value: str
    source_text: str
    critical: bool

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "claim node ID")
        _require_text(self.normalized_value, "claim node normalized value")
        _require_text(self.source_text, "claim node source text")


@dataclass(frozen=True)
class EvidenceNode:
    source_id: str
    title: str
    kind: str
    authority: EvidenceAuthority
    content: str
    provenance: EvidenceProvenance | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_id, "evidence node source ID")
        _require_text(self.title, "evidence node title")
        _require_text(self.kind, "evidence node kind")
        _require_text(self.content, "evidence node content")


@dataclass(frozen=True)
class EvidenceEdge:
    edge_id: str
    claim_id: str
    evidence_id: str
    relationship: EvidenceRelationship
    quotation: str

    def __post_init__(self) -> None:
        _require_text(self.edge_id, "evidence edge ID")
        _require_text(self.claim_id, "evidence edge claim ID")
        _require_text(self.evidence_id, "evidence edge source ID")
        _require_text(self.quotation, "evidence edge quotation")


@dataclass(frozen=True)
class EvidenceGraphSummary:
    support_count: int
    conflict_count: int
    uncertain_count: int
    authoritative_support_count: int
    authoritative_conflict_count: int


@dataclass(frozen=True)
class EvidenceGraph:
    """A validated explanatory projection, never a policy decision input."""

    claims: tuple[ClaimNode, ...]
    evidence: tuple[EvidenceNode, ...]
    edges: tuple[EvidenceEdge, ...]

    def __post_init__(self) -> None:
        claims_by_id = {claim.claim_id: claim for claim in self.claims}
        evidence_by_id = {source.source_id: source for source in self.evidence}
        edge_ids = {edge.edge_id for edge in self.edges}
        if len(claims_by_id) != len(self.claims):
            raise ValueError("Evidence graph claim IDs must be unique")
        if len(evidence_by_id) != len(self.evidence):
            raise ValueError("Evidence graph source IDs must be unique")
        if len(edge_ids) != len(self.edges):
            raise ValueError("Evidence graph edge IDs must be unique")

        for edge in self.edges:
            if edge.claim_id not in claims_by_id:
                raise ValueError(f"Unknown graph claim reference: {edge.claim_id}")
            source = evidence_by_id.get(edge.evidence_id)
            if source is None:
                raise ValueError(f"Unknown graph evidence reference: {edge.evidence_id}")
            if edge.quotation not in source.content:
                raise ValueError(f"Invented graph quotation: {edge.edge_id}")

    @property
    def summary(self) -> EvidenceGraphSummary:
        authority_by_id = {
            source.source_id: source.authority for source in self.evidence
        }
        return EvidenceGraphSummary(
            support_count=sum(
                edge.relationship is EvidenceRelationship.SUPPORTS
                for edge in self.edges
            ),
            conflict_count=sum(
                edge.relationship is EvidenceRelationship.CONFLICTS
                for edge in self.edges
            ),
            uncertain_count=sum(
                edge.relationship is EvidenceRelationship.UNCERTAIN
                for edge in self.edges
            ),
            authoritative_support_count=sum(
                edge.relationship is EvidenceRelationship.SUPPORTS
                and authority_by_id[edge.evidence_id].is_authoritative
                for edge in self.edges
            ),
            authoritative_conflict_count=sum(
                edge.relationship is EvidenceRelationship.CONFLICTS
                and authority_by_id[edge.evidence_id].is_authoritative
                for edge in self.edges
            ),
        )
