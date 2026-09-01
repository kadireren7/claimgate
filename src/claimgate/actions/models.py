"""Vendor-neutral typed models for authorizing irreversible agent actions.

SIGN_DOCUMENT is the first concrete ActionType and the only one with a real
external execution adapter (see ``claimgate.actions.adapters``). Every other
ActionType is simulated/demo-only in this phase.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from claimgate.domain.models import PolicyOutcome, validate_sha256


class ActionType(str, Enum):
    SIGN_DOCUMENT = "SIGN_DOCUMENT"
    SEND_EMAIL = "SEND_EMAIL"
    DEPLOY_SOFTWARE = "DEPLOY_SOFTWARE"
    EXECUTE_PURCHASE = "EXECUTE_PURCHASE"
    EXECUTE_PAYMENT = "EXECUTE_PAYMENT"
    DATABASE_WRITE = "DATABASE_WRITE"


class ActionRisk(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    IRREVERSIBLE = "IRREVERSIBLE"


# Static, code-only table: the single source of truth for risk classification.
# Risk is application-controlled, never LLM- or caller-controlled: ProposedAction
# validates against this table at construction time (see _risk_matches_static_table
# below), so no caller can assign a mismatched risk level to an action type.
ACTION_RISK_BY_TYPE: Mapping[ActionType, ActionRisk] = MappingProxyType(
    {
        ActionType.SIGN_DOCUMENT: ActionRisk.IRREVERSIBLE,
        ActionType.EXECUTE_PAYMENT: ActionRisk.IRREVERSIBLE,
        ActionType.EXECUTE_PURCHASE: ActionRisk.IRREVERSIBLE,
        ActionType.DEPLOY_SOFTWARE: ActionRisk.HIGH,
        ActionType.DATABASE_WRITE: ActionRisk.HIGH,
        ActionType.SEND_EMAIL: ActionRisk.MODERATE,
    }
)


class StrictActionModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


ActionParameterValue = str | int | float | bool


class ProposedAction(StrictActionModel):
    """A typed request to perform one agent action.

    Every field that materially describes the action (type, target, parameters,
    and the artifact/evidence/policy bindings) is part of the canonical action
    hash computed in ``claimgate.actions.authorization``, so any change to any of
    them is detectable. No mutable execution status is stored on this model.
    """

    action_id: str = Field(min_length=1, max_length=128)
    action_type: ActionType
    description: str = Field(min_length=1, max_length=500)
    actor: str = Field(min_length=1, max_length=200)
    target: str = Field(min_length=1, max_length=500)
    parameters: dict[str, ActionParameterValue] = Field(default_factory=dict)
    risk: ActionRisk
    artifact_sha256: tuple[str, ...] = Field(default_factory=tuple)
    evidence_sha256: str | None = None
    baseline_policy_version: str | None = None
    policy_profile_id: str | None = None
    policy_profile_sha256: str | None = None
    created_at: datetime

    @field_validator("artifact_sha256")
    @classmethod
    def _validate_artifact_hashes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for item in value:
            validate_sha256(item, "artifact_sha256")
        return value

    @field_validator("evidence_sha256", "policy_profile_sha256")
    @classmethod
    def _validate_optional_hash(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is not None:
            validate_sha256(value, info.field_name)
        return value

    @field_validator("created_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def _risk_matches_static_table(self) -> ProposedAction:
        expected = ACTION_RISK_BY_TYPE[self.action_type]
        if self.risk is not expected:
            raise ValueError(f"risk must be {expected.value} for {self.action_type.value}")
        return self


def create_proposed_action(
    *,
    action_type: ActionType,
    description: str,
    actor: str,
    target: str,
    parameters: Mapping[str, ActionParameterValue] | None = None,
    artifact_sha256: Sequence[str] = (),
    evidence_sha256: str | None = None,
    baseline_policy_version: str | None = None,
    policy_profile_id: str | None = None,
    policy_profile_sha256: str | None = None,
    action_id: str | None = None,
    created_at: datetime | None = None,
) -> ProposedAction:
    """The supported way to build a ProposedAction.

    Fills ``risk`` from the static ``ACTION_RISK_BY_TYPE`` table, so callers never
    supply it directly and cannot assign an action type a risk level other than its
    fixed classification.
    """

    return ProposedAction(
        action_id=action_id or uuid4().hex,
        action_type=action_type,
        description=description,
        actor=actor,
        target=target,
        parameters=dict(parameters or {}),
        risk=ACTION_RISK_BY_TYPE[action_type],
        artifact_sha256=tuple(artifact_sha256),
        evidence_sha256=evidence_sha256,
        baseline_policy_version=baseline_policy_version,
        policy_profile_id=policy_profile_id,
        policy_profile_sha256=policy_profile_sha256,
        created_at=created_at or datetime.now(timezone.utc),
    )


class AuthorizationBlocker(StrictActionModel):
    code: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=300)


class ExecutionCapability(StrictActionModel):
    action_type: ActionType
    supported: bool
    live_execution: bool
    adapter: str = Field(min_length=1, max_length=40)


class AuthorizationDecision(StrictActionModel):
    action_id: str
    action_type: ActionType
    action_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    outcome: PolicyOutcome
    blockers: tuple[AuthorizationBlocker, ...] = ()
    requires_human_approval: bool
    execution_capability: ExecutionCapability

    @model_validator(mode="after")
    def _blockers_match_outcome(self) -> AuthorizationDecision:
        if self.outcome is PolicyOutcome.READY_FOR_APPROVAL and self.blockers:
            raise ValueError("A ready authorization decision cannot contain blockers")
        if self.outcome is PolicyOutcome.BLOCKED and not self.blockers:
            raise ValueError("A blocked authorization decision requires blockers")
        return self


class ActionBinding(StrictActionModel):
    """The approval-binding surface for a ProposedAction.

    Every material field on ProposedAction is already part of ``action_sha256``, so
    binding equality reduces to comparing ``action_sha256`` (plus the human-readable
    action_id/action_type, included for observability). Any change to action_type,
    target, parameters, or the artifact/evidence/policy hashes changes the hash and
    therefore invalidates a prior binding.
    """

    action_id: str = Field(min_length=1, max_length=128)
    action_type: ActionType
    action_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @classmethod
    def for_action(cls, action: ProposedAction) -> ActionBinding:
        from claimgate.actions.authorization import action_sha256 as compute_action_sha256

        return cls(
            action_id=action.action_id,
            action_type=action.action_type,
            action_sha256=compute_action_sha256(action),
        )


class ActionApprovalRecord(StrictActionModel):
    """Human approval bound to the exact canonical action hash."""

    binding: ActionBinding
    approved_by: str = Field(min_length=1, max_length=200)
    approved_at: datetime

    @field_validator("approved_at")
    @classmethod
    def _require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        return value

    @classmethod
    def approve(
        cls,
        action: ProposedAction,
        *,
        approved_by: str,
        approved_at: datetime | None = None,
    ) -> ActionApprovalRecord:
        return cls(
            binding=ActionBinding.for_action(action),
            approved_by=approved_by,
            approved_at=approved_at or datetime.now(timezone.utc),
        )


def is_approval_valid(approval: ActionApprovalRecord, action: ProposedAction) -> bool:
    return approval.binding == ActionBinding.for_action(action)
