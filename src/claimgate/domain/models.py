"""Immutable domain models for policy evaluation and approval binding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from string import hexdigits


class ClaimCategory(str, Enum):
    PARTY_IDENTITY = "party_identity"
    MONEY = "money"
    QUANTITY = "quantity"
    DATES = "dates"
    DELIVERABLES = "deliverables"
    SCOPE = "scope"
    OBLIGATIONS = "obligations"
    OTHER = "other"


CRITICAL_CLAIM_CATEGORIES = frozenset(
    {
        ClaimCategory.PARTY_IDENTITY,
        ClaimCategory.MONEY,
        ClaimCategory.QUANTITY,
        ClaimCategory.DATES,
        ClaimCategory.DELIVERABLES,
        ClaimCategory.SCOPE,
        ClaimCategory.OBLIGATIONS,
    }
)


class VerificationStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    CONFLICTING = "CONFLICTING"
    UNSUPPORTED = "UNSUPPORTED"
    UNCERTAIN = "UNCERTAIN"
    FAILED = "FAILED"


class PolicyOutcome(str, Enum):
    BLOCKED = "BLOCKED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"


class WorkflowState(str, Enum):
    CREATED = "CREATED"
    GENERATING = "GENERATING"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    APPROVED = "APPROVED"
    SENDING = "SENDING"
    SENT = "SENT"
    SEND_FAILED = "SEND_FAILED"


def validate_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(character not in hexdigits for character in value):
        raise ValueError(f"{field_name} must be a 64-character SHA-256 hex digest")
    if value != value.lower():
        raise ValueError(f"{field_name} must use lowercase hex")


def _require_text(value: str, field_name: str) -> None:
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class Claim:
    claim_id: str
    text: str
    category: ClaimCategory

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "claim_id")
        _require_text(self.text, "claim text")

    @property
    def is_critical(self) -> bool:
        return self.category in CRITICAL_CLAIM_CATEGORIES


@dataclass(frozen=True)
class EvidenceSource:
    source_id: str
    title: str
    content: str

    def __post_init__(self) -> None:
        _require_text(self.source_id, "source_id")
        _require_text(self.title, "evidence title")
        _require_text(self.content, "evidence content")


@dataclass(frozen=True)
class VerificationResult:
    claim_id: str
    status: VerificationStatus
    evidence_id: str | None = None
    quotation: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.claim_id, "verification claim_id")
        if self.evidence_id is not None:
            _require_text(self.evidence_id, "verification evidence_id")
        if self.quotation is not None:
            _require_text(self.quotation, "verification quotation")


@dataclass(frozen=True)
class VerificationSnapshot:
    pdf_sha256: str
    evidence_sha256: str
    results: tuple[VerificationResult, ...]
    succeeded: bool = True
    failure_reason: str | None = None

    def __post_init__(self) -> None:
        validate_sha256(self.pdf_sha256, "verification pdf_sha256")
        validate_sha256(self.evidence_sha256, "verification evidence_sha256")


@dataclass(frozen=True)
class PolicyBlocker:
    code: str
    message: str
    claim_id: str | None = None
    evidence_id: str | None = None


@dataclass(frozen=True)
class PolicyDecision:
    outcome: PolicyOutcome
    pdf_sha256: str
    evidence_sha256: str
    policy_version: str
    blockers: tuple[PolicyBlocker, ...]

    def __post_init__(self) -> None:
        validate_sha256(self.pdf_sha256, "decision pdf_sha256")
        validate_sha256(self.evidence_sha256, "decision evidence_sha256")
        _require_text(self.policy_version, "policy_version")
        if self.outcome is PolicyOutcome.READY_FOR_APPROVAL and self.blockers:
            raise ValueError("A ready decision cannot contain blockers")
        if self.outcome is PolicyOutcome.BLOCKED and not self.blockers:
            raise ValueError("A blocked decision must contain at least one blocker")

    @property
    def binding(self) -> tuple[str, str, str]:
        return self.pdf_sha256, self.evidence_sha256, self.policy_version


@dataclass(frozen=True)
class ApprovalRecord:
    approved_by: str
    approved_at: datetime
    pdf_sha256: str
    evidence_sha256: str
    policy_version: str

    def __post_init__(self) -> None:
        _require_text(self.approved_by, "approved_by")
        if self.approved_at.tzinfo is None or self.approved_at.utcoffset() is None:
            raise ValueError("approved_at must be timezone-aware")
        validate_sha256(self.pdf_sha256, "approval pdf_sha256")
        validate_sha256(self.evidence_sha256, "approval evidence_sha256")
        _require_text(self.policy_version, "approval policy_version")

    @classmethod
    def for_decision(
        cls,
        *,
        approved_by: str,
        approved_at: datetime,
        decision: PolicyDecision,
    ) -> ApprovalRecord:
        return cls(
            approved_by=approved_by,
            approved_at=approved_at,
            pdf_sha256=decision.pdf_sha256,
            evidence_sha256=decision.evidence_sha256,
            policy_version=decision.policy_version,
        )

    @property
    def binding(self) -> tuple[str, str, str]:
        return self.pdf_sha256, self.evidence_sha256, self.policy_version

