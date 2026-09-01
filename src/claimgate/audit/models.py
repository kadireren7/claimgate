"""Strict Decision Receipt models with no runtime-only or secret fields."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from claimgate.actions import ActionRisk, ActionType, ExecutionCapability
from claimgate.domain import ClaimCategory, VerificationStatus, WorkflowState
from claimgate.evidence_graph import EvidenceAuthority, EvidenceSourceType

RECEIPT_VERSION = "claimgate-decision-receipt-v3"


class StrictReceiptModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


def _sorted_unique(values: object) -> object:
    if isinstance(values, (list, tuple, set, frozenset)):
        return tuple(sorted(set(values)))
    return values


class ReceiptClaimSummary(StrictReceiptModel):
    claim_id: str = Field(min_length=1)
    category: ClaimCategory = Field(strict=False)
    normalized_value: str = Field(min_length=1)
    critical: bool
    verification_status: VerificationStatus = Field(strict=False)
    supporting_source_ids: tuple[str, ...] = ()
    conflicting_source_ids: tuple[str, ...] = ()

    @field_validator("supporting_source_ids", "conflicting_source_ids", mode="before")
    @classmethod
    def sort_source_ids(cls, value: object) -> object:
        return _sorted_unique(value)


class ReceiptPublicEvidenceSummary(StrictReceiptModel):
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    source_url: str = Field(min_length=8)
    domain: str = Field(min_length=1)
    retrieved_at: datetime
    query: str = Field(min_length=1)
    authority: EvidenceAuthority = Field(strict=False)
    source_type: EvidenceSourceType = Field(strict=False)

    @field_validator("retrieved_at")
    @classmethod
    def normalize_retrieved_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Public evidence retrieval time must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def public_authority_is_external(self) -> ReceiptPublicEvidenceSummary:
        if self.authority in {
            EvidenceAuthority.AUTHORITATIVE_INTERNAL,
            EvidenceAuthority.INTERNAL,
        }:
            raise ValueError("Receipt public evidence authority must be external")
        return self


class ReceiptEvidenceSummary(StrictReceiptModel):
    evidence_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_ids: tuple[str, ...]
    public_sources: tuple[ReceiptPublicEvidenceSummary, ...] = ()

    @field_validator("source_ids", mode="before")
    @classmethod
    def sort_source_ids(cls, value: object) -> object:
        return _sorted_unique(value)

    @field_validator("public_sources", mode="before")
    @classmethod
    def sort_public_sources(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(
                sorted(
                    value,
                    key=lambda item: (
                        item.source_id
                        if isinstance(item, ReceiptPublicEvidenceSummary)
                        else item["source_id"]
                    ),
                )
            )
        return value


class ReceiptPolicySummary(StrictReceiptModel):
    baseline_policy_version: str = Field(min_length=1)
    policy_profile_id: str = Field(min_length=1)
    policy_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ReceiptApprovalSummary(StrictReceiptModel):
    occurred: bool
    approved_at: datetime | None = None
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    baseline_policy_version: str | None = None
    policy_profile_id: str | None = None
    policy_profile_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("approved_at")
    @classmethod
    def normalize_approval_time(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def approval_fields_match_occurrence(self) -> ReceiptApprovalSummary:
        bound_fields = (
            self.approved_at,
            self.pdf_sha256,
            self.evidence_sha256,
            self.baseline_policy_version,
            self.policy_profile_id,
            self.policy_profile_sha256,
        )
        if self.occurred and any(value is None for value in bound_fields):
            raise ValueError("An approval receipt requires every approval binding field")
        if not self.occurred and any(value is not None for value in bound_fields):
            raise ValueError("An unapproved receipt cannot contain approval binding fields")
        return self


class ReceiptESignStatus(str, Enum):
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    SENT = "SENT"
    SEND_FAILED = "SEND_FAILED"


class ReceiptDecision(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class ReceiptESignSummary(StrictReceiptModel):
    status: ReceiptESignStatus = Field(strict=False)
    foxit_identifier: str | None = None

    @model_validator(mode="after")
    def identifier_matches_status(self) -> ReceiptESignSummary:
        if self.status is ReceiptESignStatus.SENT and not self.foxit_identifier:
            raise ValueError("A sent receipt requires the Foxit identifier")
        if self.status is not ReceiptESignStatus.SENT and self.foxit_identifier is not None:
            raise ValueError("Only a sent receipt may contain a Foxit identifier")
        return self


class DecisionReceipt(StrictReceiptModel):
    receipt_version: Literal[RECEIPT_VERSION] = RECEIPT_VERSION
    run_id: str = Field(min_length=1)
    created_at: datetime
    workflow_state: WorkflowState = Field(strict=False)
    final_decision: ReceiptDecision = Field(strict=False)
    blocker_codes: tuple[str, ...]
    pdf_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pdf_filename: str = Field(min_length=1, max_length=255)
    evidence: ReceiptEvidenceSummary
    policy: ReceiptPolicySummary
    claims: tuple[ReceiptClaimSummary, ...]
    approval: ReceiptApprovalSummary
    esign: ReceiptESignSummary
    action_id: str = Field(min_length=1, max_length=128)
    action_type: ActionType = Field(strict=False)
    action_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_target: str = Field(min_length=1, max_length=500)
    action_risk: ActionRisk = Field(strict=False)
    execution_capability: ExecutionCapability
    previous_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value.astimezone(timezone.utc)

    @field_validator("blocker_codes", mode="before")
    @classmethod
    def sort_blocker_codes(cls, value: object) -> object:
        return _sorted_unique(value)

    @field_validator("claims", mode="before")
    @classmethod
    def sort_claims(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(
                sorted(
                    value,
                    key=lambda item: (
                        item.claim_id if isinstance(item, ReceiptClaimSummary) else item["claim_id"]
                    ),
                )
            )
        return value

    @model_validator(mode="after")
    def lifecycle_summaries_match_workflow(self) -> DecisionReceipt:
        approved_states = {
            WorkflowState.APPROVED,
            WorkflowState.SENDING,
            WorkflowState.SENT,
            WorkflowState.SEND_FAILED,
        }
        if self.approval.occurred is not (self.workflow_state in approved_states):
            raise ValueError("Receipt approval state conflicts with workflow state")
        expected_esign = {
            WorkflowState.SENT: ReceiptESignStatus.SENT,
            WorkflowState.SEND_FAILED: ReceiptESignStatus.SEND_FAILED,
        }.get(self.workflow_state, ReceiptESignStatus.NOT_ATTEMPTED)
        if self.esign.status is not expected_esign:
            raise ValueError("Receipt eSign status conflicts with workflow state")
        return self


class ReceiptVerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    TAMPERED = "TAMPERED"


class ReceiptVerificationResult(StrictReceiptModel):
    status: ReceiptVerificationStatus = Field(strict=False)
    receipt_sha256: str
    computed_receipt_sha256: str
    blocker_codes: tuple[str, ...]

    @field_validator("blocker_codes", mode="before")
    @classmethod
    def sort_blocker_codes(cls, value: object) -> object:
        return _sorted_unique(value)
