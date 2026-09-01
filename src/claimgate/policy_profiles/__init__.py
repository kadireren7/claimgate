"""Strict policy-as-code profiles layered above the Phase 1 baseline."""

from claimgate.policy_profiles.builtins import (
    BUILT_IN_PROFILES,
    FINANCIAL_HIGH_RISK,
    PROCUREMENT_STRICT,
    PUBLIC_EVIDENCE_STRICT,
    STANDARD_CONTRACT,
    BuiltInPolicyProfile,
    get_builtin_profile,
)
from claimgate.policy_profiles.evaluator import PolicyProfileEvaluator
from claimgate.policy_profiles.loader import (
    PolicyConfigurationError,
    PolicyProfileLoader,
)
from claimgate.policy_profiles.models import (
    CategoryRule,
    EffectivePolicyEvaluation,
    PolicyCategory,
    PolicyEvaluationContext,
    PolicyProfile,
    ProfilePolicyBlocker,
    ProfilePolicyDecision,
    ProfilePolicyOutcome,
    SourceAuthorityRequirement,
)

__all__ = [
    "BUILT_IN_PROFILES",
    "FINANCIAL_HIGH_RISK",
    "PROCUREMENT_STRICT",
    "PUBLIC_EVIDENCE_STRICT",
    "STANDARD_CONTRACT",
    "BuiltInPolicyProfile",
    "CategoryRule",
    "EffectivePolicyEvaluation",
    "PolicyCategory",
    "PolicyConfigurationError",
    "PolicyEvaluationContext",
    "PolicyProfile",
    "PolicyProfileEvaluator",
    "PolicyProfileLoader",
    "ProfilePolicyBlocker",
    "ProfilePolicyDecision",
    "ProfilePolicyOutcome",
    "SourceAuthorityRequirement",
    "get_builtin_profile",
]
