"""Validated built-in organization policy profiles."""

from __future__ import annotations

from enum import Enum

from claimgate.evidence_graph import EvidenceAuthority
from claimgate.policy_profiles.models import (
    CategoryRule,
    PolicyCategory,
    PolicyProfile,
)


class BuiltInPolicyProfile(str, Enum):
    STANDARD_CONTRACT = "standard-contract-v1"
    FINANCIAL_HIGH_RISK = "financial-high-risk-v1"
    PROCUREMENT_STRICT = "procurement-strict-v1"
    PUBLIC_EVIDENCE_STRICT = "public-evidence-strict-v1"


def _standard_rules() -> dict[PolicyCategory, CategoryRule]:
    return {
        category: CategoryRule(critical=True, minimum_supporting_sources=1)
        for category in (
            PolicyCategory.PARTY_IDENTITY,
            PolicyCategory.MONEY,
            PolicyCategory.QUANTITY,
            PolicyCategory.DELIVERY_DATE,
            PolicyCategory.DELIVERABLES,
            PolicyCategory.SCOPE,
        )
    }


STANDARD_CONTRACT = PolicyProfile(
    id=BuiltInPolicyProfile.STANDARD_CONTRACT.value,
    name="Standard Contract",
    description="Baseline-aligned checks requiring one supporting source per material term.",
    categories=_standard_rules(),
)

FINANCIAL_HIGH_RISK = PolicyProfile(
    id=BuiltInPolicyProfile.FINANCIAL_HIGH_RISK.value,
    name="Financial High Risk",
    description=(
        "Requires two money sources, including authoritative internal support, with no "
        "conflicts or uncertainty."
    ),
    categories={
        **_standard_rules(),
        PolicyCategory.MONEY: CategoryRule(
            critical=True,
            minimum_supporting_sources=2,
            minimum_authoritative_sources=1,
            qualifying_authorities=(EvidenceAuthority.AUTHORITATIVE_INTERNAL,),
            allow_conflicts=False,
            allow_uncertain=False,
        ),
    },
)

PROCUREMENT_STRICT = PolicyProfile(
    id=BuiltInPolicyProfile.PROCUREMENT_STRICT.value,
    name="Procurement Strict",
    description=(
        "Requires authoritative support for procurement-critical identities, terms, "
        "deliverables, and obligations."
    ),
    categories={
        **_standard_rules(),
        **{
            category: CategoryRule(
                critical=True,
                minimum_supporting_sources=1,
                minimum_authoritative_sources=1,
                qualifying_authorities=(EvidenceAuthority.AUTHORITATIVE_INTERNAL,),
                allow_conflicts=False,
                allow_authoritative_conflicts=False,
                allow_uncertain=False,
            )
            for category in (
                PolicyCategory.PARTY_IDENTITY,
                PolicyCategory.MONEY,
                PolicyCategory.QUANTITY,
                PolicyCategory.DELIVERY_DATE,
                PolicyCategory.DELIVERABLES,
                PolicyCategory.OBLIGATIONS,
            )
        },
    },
)

PUBLIC_EVIDENCE_STRICT = PolicyProfile(
    id=BuiltInPolicyProfile.PUBLIC_EVIDENCE_STRICT.value,
    name="Public Evidence Strict",
    description=(
        "Requires public assertions to have VERIFIED_EXTERNAL support; an unknown blog "
        "cannot be the sole source."
    ),
    categories={
        **_standard_rules(),
        PolicyCategory.OTHER: CategoryRule(
            critical=False,
            minimum_supporting_sources=1,
            minimum_authoritative_sources=1,
            qualifying_authorities=(EvidenceAuthority.VERIFIED_EXTERNAL,),
            allow_conflicts=False,
            allow_uncertain=False,
        ),
    },
)

BUILT_IN_PROFILES = {
    BuiltInPolicyProfile.STANDARD_CONTRACT: STANDARD_CONTRACT,
    BuiltInPolicyProfile.FINANCIAL_HIGH_RISK: FINANCIAL_HIGH_RISK,
    BuiltInPolicyProfile.PROCUREMENT_STRICT: PROCUREMENT_STRICT,
    BuiltInPolicyProfile.PUBLIC_EVIDENCE_STRICT: PUBLIC_EVIDENCE_STRICT,
}


def get_builtin_profile(identifier: BuiltInPolicyProfile | str) -> PolicyProfile:
    try:
        typed_identifier = (
            identifier
            if isinstance(identifier, BuiltInPolicyProfile)
            else BuiltInPolicyProfile(identifier)
        )
    except ValueError as exc:
        raise ValueError(f"Unknown built-in policy profile: {identifier}") from exc
    return BUILT_IN_PROFILES[typed_identifier]
