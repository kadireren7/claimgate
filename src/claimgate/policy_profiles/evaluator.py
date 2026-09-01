"""Deterministic evaluation of validated Evidence Graphs against profiles."""

from __future__ import annotations

from collections import defaultdict

from claimgate.domain import PolicyBlocker, PolicyDecision, PolicyOutcome
from claimgate.evidence_graph import EvidenceRelationship
from claimgate.policy_profiles.models import (
    EffectivePolicyEvaluation,
    PolicyEvaluationContext,
    ProfilePolicyBlocker,
    ProfilePolicyDecision,
    ProfilePolicyOutcome,
)


class PolicyProfileEvaluator:
    """Apply declarative thresholds with no semantic inference or tools."""

    def evaluate(self, context: PolicyEvaluationContext) -> EffectivePolicyEvaluation:
        profile_decision = self.evaluate_profile(context)
        baseline = context.baseline_decision
        if baseline.outcome is PolicyOutcome.BLOCKED:
            final = baseline
        elif profile_decision.outcome is ProfilePolicyOutcome.BLOCK:
            final = PolicyDecision(
                outcome=PolicyOutcome.BLOCKED,
                pdf_sha256=baseline.pdf_sha256,
                evidence_sha256=baseline.evidence_sha256,
                policy_version=baseline.policy_version,
                blockers=tuple(
                    PolicyBlocker(
                        code=blocker.code,
                        message=blocker.message,
                        claim_id=blocker.claim_id,
                    )
                    for blocker in profile_decision.blockers
                ),
            )
        else:
            final = baseline
        return EffectivePolicyEvaluation(
            baseline_decision=baseline,
            profile_decision=profile_decision,
            final_decision=final,
        )

    def evaluate_profile(
        self, context: PolicyEvaluationContext
    ) -> ProfilePolicyDecision:
        profile = context.selected_profile
        graph = context.evidence_graph
        if graph is None:
            return self._decision(
                profile,
                [
                    ProfilePolicyBlocker(
                        code="PROFILE_EVIDENCE_GRAPH_UNAVAILABLE",
                        message="Validated Evidence Graph is unavailable",
                    )
                ],
            )

        evidence_by_id = {source.source_id: source for source in graph.evidence}
        edges_by_claim = defaultdict(list)
        for edge in graph.edges:
            edges_by_claim[edge.claim_id].append(edge)

        blockers: list[ProfilePolicyBlocker] = []
        for category, rule in sorted(
            profile.categories.items(), key=lambda item: item[0].value
        ):
            category_claims = sorted(
                (
                    claim
                    for claim in graph.claims
                    if claim.category is category.claim_category
                ),
                key=lambda claim: claim.claim_id,
            )
            if rule.critical and not category_claims:
                blockers.append(
                    ProfilePolicyBlocker(
                        code="PROFILE_REQUIRED_CATEGORY_MISSING",
                        message=f"Required category {category.value} has no material claim",
                        category=category,
                    )
                )
                continue

            for claim in category_claims:
                edges = edges_by_claim[claim.claim_id]
                supporting_source_ids = {
                    edge.evidence_id
                    for edge in edges
                    if edge.relationship is EvidenceRelationship.SUPPORTS
                }
                authoritative_support_ids = {
                    evidence_id
                    for evidence_id in supporting_source_ids
                    if evidence_by_id[evidence_id].authority
                    in rule.qualifying_authorities
                }
                conflicts = [
                    edge
                    for edge in edges
                    if edge.relationship is EvidenceRelationship.CONFLICTS
                ]
                authoritative_conflicts = [
                    edge
                    for edge in conflicts
                    if evidence_by_id[edge.evidence_id].authority
                    in rule.qualifying_authorities
                ]
                uncertain = [
                    edge
                    for edge in edges
                    if edge.relationship is EvidenceRelationship.UNCERTAIN
                ]

                if len(supporting_source_ids) < rule.minimum_supporting_sources:
                    blockers.append(
                        ProfilePolicyBlocker(
                            code="PROFILE_INSUFFICIENT_SUPPORTING_SOURCES",
                            message=(
                                f"{category.value} requires "
                                f"{rule.minimum_supporting_sources} supporting sources; "
                                f"found {len(supporting_source_ids)}"
                            ),
                            category=category,
                            claim_id=claim.claim_id,
                        )
                    )
                if (
                    len(authoritative_support_ids)
                    < rule.minimum_authoritative_sources
                ):
                    blockers.append(
                        ProfilePolicyBlocker(
                            code="PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES",
                            message=(
                                f"{category.value} requires "
                                f"{rule.minimum_authoritative_sources} authoritative sources; "
                                f"found {len(authoritative_support_ids)}"
                            ),
                            category=category,
                            claim_id=claim.claim_id,
                        )
                    )
                if conflicts and not rule.allow_conflicts:
                    blockers.append(
                        ProfilePolicyBlocker(
                            code="PROFILE_CONFLICT_NOT_ALLOWED",
                            message=f"{category.value} has conflicting evidence",
                            category=category,
                            claim_id=claim.claim_id,
                        )
                    )
                elif (
                    authoritative_conflicts
                    and not rule.allow_authoritative_conflicts
                ):
                    blockers.append(
                        ProfilePolicyBlocker(
                            code="PROFILE_AUTHORITATIVE_CONFLICT_NOT_ALLOWED",
                            message=(
                                f"{category.value} has conflicting authoritative evidence"
                            ),
                            category=category,
                            claim_id=claim.claim_id,
                        )
                    )
                if uncertain and not rule.allow_uncertain:
                    blockers.append(
                        ProfilePolicyBlocker(
                            code="PROFILE_UNCERTAIN_NOT_ALLOWED",
                            message=f"{category.value} has unresolved evidence",
                            category=category,
                            claim_id=claim.claim_id,
                        )
                    )

        return self._decision(profile, blockers)

    @staticmethod
    def _decision(profile, blockers) -> ProfilePolicyDecision:
        return ProfilePolicyDecision(
            profile_id=profile.id,
            profile_hash=profile.profile_hash,
            outcome=(
                ProfilePolicyOutcome.BLOCK if blockers else ProfilePolicyOutcome.PASS
            ),
            blockers=tuple(blockers),
        )
