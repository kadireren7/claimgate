"""Build an Evidence Graph from already validated semantic comparisons."""

from __future__ import annotations

from collections.abc import Sequence

from claimgate.evidence_graph.models import (
    ClaimNode,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    EvidenceRelationship,
)
from claimgate.semantic.evidence import EvidenceDocument
from claimgate.semantic.models import (
    EvidenceComparison,
    ExtractedClaim,
    SemanticVerificationStatus,
)

RELATIONSHIP_BY_STATUS = {
    SemanticVerificationStatus.SUPPORTED: EvidenceRelationship.SUPPORTS,
    SemanticVerificationStatus.CONFLICTING: EvidenceRelationship.CONFLICTS,
    SemanticVerificationStatus.UNCERTAIN: EvidenceRelationship.UNCERTAIN,
}


def build_evidence_graph(
    *,
    claims: Sequence[ExtractedClaim],
    evidence_documents: Sequence[EvidenceDocument],
    comparisons: Sequence[EvidenceComparison],
) -> EvidenceGraph:
    """Project validated comparisons; never ask a model or calculate policy."""

    claim_nodes = tuple(
        ClaimNode(
            claim_id=claim.claim_id,
            category=claim.category,
            normalized_value=claim.normalized_value,
            source_text=claim.source_text,
            critical=claim.critical,
        )
        for claim in claims
    )
    evidence_nodes = tuple(
        EvidenceNode(
            source_id=document.source.source_id,
            title=document.source.title,
            kind=document.kind.value,
            authority=document.authority,
            content=document.source.content,
            provenance=document.provenance,
        )
        for document in evidence_documents
    )
    edges: list[EvidenceEdge] = []
    for index, comparison in enumerate(comparisons, start=1):
        relationship = RELATIONSHIP_BY_STATUS.get(comparison.status)
        if relationship is None:
            continue
        if comparison.evidence_id is None or comparison.quotation is None:
            raise ValueError(
                f"Graph relationship lacks validated evidence: {comparison.claim_id}"
            )
        edges.append(
            EvidenceEdge(
                edge_id=f"edge-{index:03d}",
                claim_id=comparison.claim_id,
                evidence_id=comparison.evidence_id,
                relationship=relationship,
                quotation=comparison.quotation,
            )
        )
    return EvidenceGraph(
        claims=claim_nodes,
        evidence=evidence_nodes,
        edges=tuple(edges),
    )
