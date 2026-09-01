"""Strict contracts for read-only historical Decision Receipt replay."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from claimgate.actions import ActionType
from claimgate.audit import (
    ReceiptApprovalSummary,
    ReceiptDecision,
    ReceiptESignSummary,
    ReceiptPublicEvidenceSummary,
)
from claimgate.domain import WorkflowState


class StrictReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class ReplayStatus(str, Enum):
    VERIFIED = "VERIFIED"
    DRIFT_DETECTED = "DRIFT_DETECTED"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    CHAIN_BROKEN = "CHAIN_BROKEN"
    INVALID_RECEIPT = "INVALID_RECEIPT"


class ReplayCheckStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


class ReplayPreset(str, Enum):
    CLEAN_REPLAY = "CLEAN_REPLAY"
    PDF_DRIFT = "PDF_DRIFT"
    EVIDENCE_DRIFT = "EVIDENCE_DRIFT"
    POLICY_DRIFT = "POLICY_DRIFT"
    BROKEN_CHAIN = "BROKEN_CHAIN"
    ACTION_PARAMETER_DRIFT = "ACTION_PARAMETER_DRIFT"


class ReplayRequest(StrictReplayModel):
    run_id: str = Field(min_length=1, max_length=128)
    receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preset: ReplayPreset = Field(default=ReplayPreset.CLEAN_REPLAY, strict=False)


class ArtifactSnapshot(StrictReplayModel):
    """Current server-observed values; never contains paths or artifact contents."""

    pdf_available: bool
    pdf_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_available: bool
    evidence_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evidence_source_ids: tuple[str, ...]
    public_evidence: tuple[ReceiptPublicEvidenceSummary, ...] = ()
    action_id: str = Field(min_length=1, max_length=128)
    action_type: ActionType = Field(strict=False)
    action_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_policy_version: str = Field(min_length=1)
    policy_profile_id: str = Field(min_length=1)
    policy_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval: ReceiptApprovalSummary
    esign: ReceiptESignSummary
    expected_previous_receipt_sha256: str | None = Field(
        default=None, pattern=r"^[0-9a-f]{64}$"
    )

    @field_validator("evidence_source_ids", mode="before")
    @classmethod
    def canonicalize_source_ids(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted(set(value)))
        return value

    @model_validator(mode="after")
    def availability_matches_hashes(self) -> ArtifactSnapshot:
        if self.pdf_available is (self.pdf_sha256 is None):
            raise ValueError("PDF availability must match the observed PDF hash")
        if self.evidence_available is (self.evidence_sha256 is None):
            raise ValueError("Evidence availability must match the observed evidence hash")
        return self


class ReplayCheck(StrictReplayModel):
    check_id: str = Field(min_length=1, max_length=80)
    label: str = Field(min_length=1, max_length=120)
    expected_value: str
    observed_value: str
    status: ReplayCheckStatus = Field(strict=False)
    blocker_code: str | None = Field(default=None, max_length=100)
    explanation: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def failure_has_blocker(self) -> ReplayCheck:
        if self.status is ReplayCheckStatus.FAIL and self.blocker_code is None:
            raise ValueError("A failed replay check requires a blocker code")
        if self.status is ReplayCheckStatus.PASS and self.blocker_code is not None:
            raise ValueError("A passing replay check cannot have a blocker code")
        return self


class ReplayResult(StrictReplayModel):
    run_id: str
    receipt_sha256: str
    original_final_decision: ReceiptDecision = Field(strict=False)
    original_workflow_state: WorkflowState = Field(strict=False)
    status: ReplayStatus = Field(strict=False)
    checks: tuple[ReplayCheck, ...]
    blocker_codes: tuple[str, ...]

    @field_validator("blocker_codes", mode="before")
    @classmethod
    def canonicalize_blockers(cls, value: object) -> object:
        if isinstance(value, (list, tuple, set, frozenset)):
            return tuple(sorted(set(value)))
        return value


class AuditEventKind(str, Enum):
    RUN_CREATED = "RUN_CREATED"
    VERIFICATION_RECEIPT = "VERIFICATION_RECEIPT"
    PUBLIC_EVIDENCE_REEVALUATION = "PUBLIC_EVIDENCE_REEVALUATION"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    ESIGN_ATTEMPT = "ESIGN_ATTEMPT"
    SEND_RECEIPT = "SEND_RECEIPT"


class AuditTimelineEvent(StrictReplayModel):
    event_id: str = Field(min_length=1, max_length=160)
    kind: AuditEventKind = Field(strict=False)
    timestamp: datetime
    state: WorkflowState = Field(strict=False)
    receipt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    decision: ReceiptDecision | None = Field(default=None, strict=False)
    blocker_codes: tuple[str, ...] = ()
    detail: str = Field(min_length=1, max_length=500)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timeline timestamps must be timezone-aware")
        return value.astimezone(timezone.utc)
