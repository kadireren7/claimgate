"""Strict, non-executable policy-as-code configuration models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from claimgate.domain import ClaimCategory, PolicyDecision, PolicyOutcome
from claimgate.evidence_graph import EvidenceAuthority, EvidenceGraph


class PolicyCategory(str, Enum):
    PARTY_IDENTITY = "party_identity"
    MONEY = "money"
    QUANTITY = "quantity"
    DELIVERY_DATE = "delivery_date"
    DELIVERABLES = "deliverables"
    SCOPE = "scope"
    OBLIGATIONS = "obligations"
    OTHER = "other"

    @property
    def claim_category(self) -> ClaimCategory:
        if self is PolicyCategory.DELIVERY_DATE:
            return ClaimCategory.DATES
        return ClaimCategory(self.value)


class StrictPolicyModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SourceAuthorityRequirement(StrictPolicyModel):
    minimum_authoritative_sources: int = Field(default=0, ge=0, le=8)
    qualifying_authorities: tuple[EvidenceAuthority, ...] = Field(
        default=(EvidenceAuthority.AUTHORITATIVE_INTERNAL,),
        min_length=1,
        max_length=4,
    )
    allow_authoritative_conflicts: bool = False

    @field_validator("qualifying_authorities", mode="before")
    @classmethod
    def parse_authorities(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        try:
            return tuple(
                item if isinstance(item, EvidenceAuthority) else EvidenceAuthority(item)
                for item in value
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Unknown evidence authority") from exc

    @model_validator(mode="after")
    def authority_levels_must_be_unique(self) -> SourceAuthorityRequirement:
        if len(set(self.qualifying_authorities)) != len(self.qualifying_authorities):
            raise ValueError("qualifying_authorities must be unique")
        return self


class CategoryRule(SourceAuthorityRequirement):
    critical: bool
    minimum_supporting_sources: int = Field(default=1, ge=0, le=8)
    allow_conflicts: bool = False
    allow_uncertain: bool = False

    @model_validator(mode="after")
    def authoritative_minimum_must_fit_support_minimum(self) -> CategoryRule:
        if self.minimum_authoritative_sources > self.minimum_supporting_sources:
            raise ValueError(
                "minimum_authoritative_sources cannot exceed "
                "minimum_supporting_sources"
            )
        return self


class PolicyProfile(StrictPolicyModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=240)
    categories: dict[PolicyCategory, CategoryRule] = Field(
        min_length=1, max_length=8
    )

    @field_validator("categories", mode="before")
    @classmethod
    def parse_categories(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        parsed: dict[PolicyCategory, object] = {}
        for category, rule in value.items():
            try:
                typed_category = (
                    category
                    if isinstance(category, PolicyCategory)
                    else PolicyCategory(category)
                )
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Unknown policy category: {category}") from exc
            if typed_category in parsed:
                raise ValueError(f"Duplicate policy category: {typed_category.value}")
            parsed[typed_category] = rule
        return parsed

    @property
    def profile_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


class ProfilePolicyOutcome(str, Enum):
    PASS = "PASS"
    BLOCK = "BLOCK"


class ProfilePolicyBlocker(StrictPolicyModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)
    category: PolicyCategory | None = None
    claim_id: str | None = None


class ProfilePolicyDecision(StrictPolicyModel):
    profile_id: str
    profile_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: ProfilePolicyOutcome
    blockers: tuple[ProfilePolicyBlocker, ...]

    @model_validator(mode="after")
    def blockers_must_match_outcome(self) -> ProfilePolicyDecision:
        if self.outcome is ProfilePolicyOutcome.PASS and self.blockers:
            raise ValueError("A passing profile decision cannot contain blockers")
        if self.outcome is ProfilePolicyOutcome.BLOCK and not self.blockers:
            raise ValueError("A blocked profile decision requires blockers")
        return self


@dataclass(frozen=True)
class PolicyEvaluationContext:
    baseline_decision: PolicyDecision
    selected_profile: PolicyProfile
    evidence_graph: EvidenceGraph | None


@dataclass(frozen=True)
class EffectivePolicyEvaluation:
    baseline_decision: PolicyDecision
    profile_decision: ProfilePolicyDecision
    final_decision: PolicyDecision

    def __post_init__(self) -> None:
        if (
            self.baseline_decision.outcome is PolicyOutcome.BLOCKED
            and self.final_decision.outcome is not PolicyOutcome.BLOCKED
        ):
            raise ValueError("A profile cannot override a blocked baseline decision")
