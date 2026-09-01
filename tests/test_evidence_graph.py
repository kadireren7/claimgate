from __future__ import annotations

import pytest

from claimgate.domain import ClaimCategory
from claimgate.evidence_graph import (
    ClaimNode,
    EvidenceAuthority,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    EvidenceRelationship,
)


def claim_node() -> ClaimNode:
    return ClaimNode(
        claim_id="money",
        category=ClaimCategory.MONEY,
        normalized_value="USD 12500.00",
        source_text="Contract amount: USD 12,500.00",
        critical=True,
    )


def evidence_node() -> EvidenceNode:
    return EvidenceNode(
        source_id="quote",
        title="Approved quote",
        kind="pdf_derived_text",
        authority=EvidenceAuthority.AUTHORITATIVE_INTERNAL,
        content="Contract amount: USD 12,500.00",
    )


def test_graph_rejects_invented_quotation_edge() -> None:
    edge = EvidenceEdge(
        edge_id="edge-001",
        claim_id="money",
        evidence_id="quote",
        relationship=EvidenceRelationship.SUPPORTS,
        quotation="Contract amount: USD 99,999.00",
    )

    with pytest.raises(ValueError, match="Invented graph quotation"):
        EvidenceGraph(claims=(claim_node(),), evidence=(evidence_node(),), edges=(edge,))


@pytest.mark.parametrize(
    ("claim_id", "evidence_id", "message"),
    [
        ("unknown-claim", "quote", "Unknown graph claim reference"),
        ("money", "unknown-source", "Unknown graph evidence reference"),
    ],
)
def test_graph_rejects_unknown_references(
    claim_id: str, evidence_id: str, message: str
) -> None:
    edge = EvidenceEdge(
        edge_id="edge-001",
        claim_id=claim_id,
        evidence_id=evidence_id,
        relationship=EvidenceRelationship.SUPPORTS,
        quotation="Contract amount: USD 12,500.00",
    )

    with pytest.raises(ValueError, match=message):
        EvidenceGraph(claims=(claim_node(),), evidence=(evidence_node(),), edges=(edge,))


def test_graph_summary_counts_relationships_and_authority_deterministically() -> None:
    source = evidence_node()
    support = EvidenceEdge(
        edge_id="edge-support",
        claim_id="money",
        evidence_id=source.source_id,
        relationship=EvidenceRelationship.SUPPORTS,
        quotation=source.content,
    )
    conflict = EvidenceEdge(
        edge_id="edge-conflict",
        claim_id="money",
        evidence_id=source.source_id,
        relationship=EvidenceRelationship.CONFLICTS,
        quotation=source.content,
    )
    graph = EvidenceGraph(
        claims=(claim_node(),), evidence=(source,), edges=(support, conflict)
    )

    assert graph.summary.support_count == 1
    assert graph.summary.conflict_count == 1
    assert graph.summary.uncertain_count == 0
    assert graph.summary.authoritative_support_count == 1
    assert graph.summary.authoritative_conflict_count == 1
