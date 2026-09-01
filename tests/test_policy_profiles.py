from __future__ import annotations

from pathlib import Path

import pytest

from claimgate.domain import (
    POLICY_VERSION,
    ClaimCategory,
    PolicyBlocker,
    PolicyDecision,
    PolicyOutcome,
)
from claimgate.evidence_graph import (
    ClaimNode,
    EvidenceAuthority,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    EvidenceRelationship,
)
from claimgate.policy_profiles import (
    FINANCIAL_HIGH_RISK,
    STANDARD_CONTRACT,
    CategoryRule,
    PolicyCategory,
    PolicyConfigurationError,
    PolicyEvaluationContext,
    PolicyProfile,
    PolicyProfileEvaluator,
    PolicyProfileLoader,
    ProfilePolicyOutcome,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def baseline(outcome: PolicyOutcome = PolicyOutcome.READY_FOR_APPROVAL) -> PolicyDecision:
    blockers = (
        ()
        if outcome is PolicyOutcome.READY_FOR_APPROVAL
        else (PolicyBlocker(code="BASELINE_BLOCK", message="Baseline rejected"),)
    )
    return PolicyDecision(
        outcome=outcome,
        pdf_sha256=HASH_A,
        evidence_sha256=HASH_B,
        policy_version=POLICY_VERSION,
        blockers=blockers,
    )


def money_graph(
    authorities: tuple[EvidenceAuthority, ...], *, duplicate_first_edge: bool = False
) -> EvidenceGraph:
    claim = ClaimNode(
        claim_id="money",
        category=ClaimCategory.MONEY,
        normalized_value="USD 12500.00",
        source_text="Contract amount: USD 12,500.00",
        critical=True,
    )
    sources = tuple(
        EvidenceNode(
            source_id=f"source-{index}",
            title=f"Source {index}",
            kind="plain_text",
            authority=authority,
            content=f"Approved amount {index}: USD 12,500.00",
        )
        for index, authority in enumerate(authorities, start=1)
    )
    edges = [
        EvidenceEdge(
            edge_id=f"edge-{index}",
            claim_id=claim.claim_id,
            evidence_id=source.source_id,
            relationship=EvidenceRelationship.SUPPORTS,
            quotation=source.content,
        )
        for index, source in enumerate(sources, start=1)
    ]
    if duplicate_first_edge and sources:
        edges.append(
            EvidenceEdge(
                edge_id="edge-duplicate-source",
                claim_id=claim.claim_id,
                evidence_id=sources[0].source_id,
                relationship=EvidenceRelationship.SUPPORTS,
                quotation=sources[0].content,
            )
        )
    return EvidenceGraph(claims=(claim,), evidence=sources, edges=tuple(edges))


def money_only_profile(
    *, minimum_sources: int, minimum_authoritative: int = 0
) -> PolicyProfile:
    return PolicyProfile(
        id="test-money-profile-v1",
        name="Test Money Profile",
        description="A deterministic test profile.",
        categories={
            PolicyCategory.MONEY: CategoryRule(
                critical=True,
                minimum_supporting_sources=minimum_sources,
                minimum_authoritative_sources=minimum_authoritative,
            )
        },
    )


def evaluate(profile: PolicyProfile, graph: EvidenceGraph, *, baseline_decision=None):
    return PolicyProfileEvaluator().evaluate(
        PolicyEvaluationContext(
            baseline_decision=baseline_decision or baseline(),
            selected_profile=profile,
            evidence_graph=graph,
        )
    )


def test_same_evidence_passes_standard_rule_but_blocks_financial_rule() -> None:
    graph = money_graph((EvidenceAuthority.AUTHORITATIVE_INTERNAL,))
    standard_money = PolicyProfile(
        id="standard-money-v1",
        name="Standard Money",
        description="One supporting source is sufficient.",
        categories={PolicyCategory.MONEY: STANDARD_CONTRACT.categories[PolicyCategory.MONEY]},
    )
    financial_money = PolicyProfile(
        id="financial-money-v1",
        name="Financial Money",
        description="Two supporting sources are required.",
        categories={
            PolicyCategory.MONEY: FINANCIAL_HIGH_RISK.categories[PolicyCategory.MONEY]
        },
    )

    standard = evaluate(standard_money, graph)
    financial = evaluate(financial_money, graph)

    assert standard.profile_decision.outcome is ProfilePolicyOutcome.PASS
    assert standard.final_decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert financial.profile_decision.outcome is ProfilePolicyOutcome.BLOCK
    assert financial.final_decision.outcome is PolicyOutcome.BLOCKED
    assert financial.profile_decision.blockers[0].code == (
        "PROFILE_INSUFFICIENT_SUPPORTING_SOURCES"
    )


def test_profile_cannot_override_blocked_phase1_baseline() -> None:
    permissive = PolicyProfile(
        id="permissive-profile-v1",
        name="Permissive Test",
        description="The profile passes, but the baseline remains authoritative.",
        categories={
            PolicyCategory.MONEY: CategoryRule(
                critical=False,
                minimum_supporting_sources=0,
                allow_conflicts=True,
                allow_authoritative_conflicts=True,
                allow_uncertain=True,
            )
        },
    )

    result = evaluate(
        permissive,
        money_graph(()),
        baseline_decision=baseline(PolicyOutcome.BLOCKED),
    )

    assert result.profile_decision.outcome is ProfilePolicyOutcome.PASS
    assert result.final_decision == result.baseline_decision
    assert result.final_decision.outcome is PolicyOutcome.BLOCKED


def test_source_count_uses_distinct_sources_not_duplicate_edges() -> None:
    graph = money_graph(
        (EvidenceAuthority.AUTHORITATIVE_INTERNAL,), duplicate_first_edge=True
    )

    result = evaluate(money_only_profile(minimum_sources=2), graph)

    assert result.profile_decision.outcome is ProfilePolicyOutcome.BLOCK
    assert "found 1" in result.profile_decision.blockers[0].message


def test_authority_requirement_is_deterministic() -> None:
    profile = money_only_profile(minimum_sources=2, minimum_authoritative=1)
    external_only = money_graph(
        (
            EvidenceAuthority.VERIFIED_EXTERNAL,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    )
    with_internal = money_graph(
        (
            EvidenceAuthority.AUTHORITATIVE_INTERNAL,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    )

    blocked = evaluate(profile, external_only)
    passed = evaluate(profile, with_internal)

    assert blocked.profile_decision.outcome is ProfilePolicyOutcome.BLOCK
    assert blocked.profile_decision.blockers[0].code == (
        "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES"
    )
    assert passed.profile_decision.outcome is ProfilePolicyOutcome.PASS


def test_valid_yaml_and_json_load_to_same_hashed_profile() -> None:
    yaml_policy = """
id: financial-high-risk-v1
name: Financial High Risk
description: Strict deterministic money checks.
categories:
  money:
    critical: true
    minimum_supporting_sources: 2
    minimum_authoritative_sources: 1
    allow_conflicts: false
    allow_uncertain: false
"""
    json_policy = """{
      "id": "financial-high-risk-v1",
      "name": "Financial High Risk",
      "description": "Strict deterministic money checks.",
      "categories": {
        "money": {
          "critical": true,
          "minimum_supporting_sources": 2,
          "minimum_authoritative_sources": 1,
          "allow_conflicts": false,
          "allow_uncertain": false
        }
      }
    }"""

    from_yaml = PolicyProfileLoader.loads(yaml_policy, format="yaml")
    from_json = PolicyProfileLoader.loads(json_policy, format="json")

    assert from_yaml == from_json
    assert from_yaml.profile_hash == from_json.profile_hash


@pytest.mark.parametrize(
    ("content", "format"),
    [
        ("id: [not valid", "yaml"),
        ('{"id":', "json"),
        ("!!python/object/apply:os.system ['echo unsafe']", "yaml"),
        ('{"id":"one","id":"two"}', "json"),
    ],
)
def test_invalid_or_executable_policy_configuration_fails_closed(
    content: str, format: str
) -> None:
    with pytest.raises(PolicyConfigurationError):
        PolicyProfileLoader.loads(content, format=format)


def test_unknown_categories_and_keys_fail_closed() -> None:
    unknown_category = """
id: invalid-profile-v1
name: Invalid
description: Contains an unknown category.
categories:
  model_invented_category:
    critical: true
"""
    executable_expression = """
id: invalid-profile-v1
name: Invalid
description: Expressions are not part of the schema.
categories:
  money:
    critical: true
    when: "python: os.system('unsafe')"
"""

    with pytest.raises(PolicyConfigurationError):
        PolicyProfileLoader.loads(unknown_category, format="yaml")
    with pytest.raises(PolicyConfigurationError):
        PolicyProfileLoader.loads(executable_expression, format="yaml")


def test_profile_hash_changes_when_contents_change_with_same_id() -> None:
    changed = STANDARD_CONTRACT.model_copy(
        update={"description": "Changed organization policy contents."}
    )

    assert changed.id == STANDARD_CONTRACT.id
    assert changed.profile_hash != STANDARD_CONTRACT.profile_hash


def test_semantic_provider_package_cannot_access_policy_configuration() -> None:
    semantic_directory = Path(__file__).parents[1] / "src" / "claimgate" / "semantic"
    semantic_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in semantic_directory.glob("*.py")
    )

    assert "policy_profiles" not in semantic_source
    assert "PolicyProfile" not in semantic_source
    assert "policy_profile_hash" not in semantic_source
