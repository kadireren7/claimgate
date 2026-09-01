"""Guarded workflow state transitions with explicit approval binding."""

from __future__ import annotations

from claimgate.domain.models import (
    ApprovalRecord,
    PolicyDecision,
    PolicyOutcome,
    WorkflowState,
    validate_sha256,
)


class InvalidTransitionError(RuntimeError):
    """Raised when a workflow transition is not allowed or its binding is invalid."""


class WorkflowRun:
    """In-memory Phase 1 aggregate; persistence is intentionally deferred."""

    def __init__(self, run_id: str) -> None:
        if not run_id.strip():
            raise ValueError("run_id must not be empty")
        self._run_id = run_id
        self._state = WorkflowState.CREATED
        self._pdf_sha256: str | None = None
        self._evidence_sha256: str | None = None
        self._decision: PolicyDecision | None = None
        self._approval: ApprovalRecord | None = None

    @property
    def run_id(self) -> str:
        return self._run_id

    @property
    def state(self) -> WorkflowState:
        return self._state

    @property
    def decision(self) -> PolicyDecision | None:
        return self._decision

    @property
    def approval(self) -> ApprovalRecord | None:
        return self._approval

    def start_generation(self) -> None:
        self._require_state(WorkflowState.CREATED)
        self._state = WorkflowState.GENERATING

    def start_verification(self, *, pdf_sha256: str, evidence_sha256: str) -> None:
        self._require_state(WorkflowState.GENERATING)
        validate_sha256(pdf_sha256, "workflow pdf_sha256")
        validate_sha256(evidence_sha256, "workflow evidence_sha256")
        self._pdf_sha256 = pdf_sha256
        self._evidence_sha256 = evidence_sha256
        self._state = WorkflowState.VERIFYING

    def apply_policy(self, decision: PolicyDecision) -> None:
        self._require_state(WorkflowState.VERIFYING)
        if decision.pdf_sha256 != self._pdf_sha256:
            raise InvalidTransitionError("Policy decision PDF hash does not match the workflow")
        if decision.evidence_sha256 != self._evidence_sha256:
            raise InvalidTransitionError(
                "Policy decision evidence hash does not match the workflow"
            )
        self._decision = decision
        self._state = (
            WorkflowState.BLOCKED
            if decision.outcome is PolicyOutcome.BLOCKED
            else WorkflowState.READY_FOR_APPROVAL
        )

    def approve(self, approval: ApprovalRecord) -> None:
        self._require_state(WorkflowState.READY_FOR_APPROVAL)
        if self._decision is None:
            raise InvalidTransitionError("Cannot approve without a policy decision")
        if approval.binding != self._decision.binding:
            raise InvalidTransitionError(
                "Approval is not bound to the decision PDF, evidence, and policy version"
            )
        self._approval = approval
        self._state = WorkflowState.APPROVED

    def start_sending(self) -> None:
        self._require_state(WorkflowState.APPROVED)
        if self._decision is None or self._approval is None:
            raise InvalidTransitionError("Explicit approval is required before sending")
        if self._approval.binding != self._decision.binding:
            raise InvalidTransitionError("Approval binding no longer matches the policy decision")
        self._state = WorkflowState.SENDING

    def mark_sent(self) -> None:
        self._require_state(WorkflowState.SENDING)
        self._state = WorkflowState.SENT

    def mark_send_failed(self) -> None:
        self._require_state(WorkflowState.SENDING)
        self._state = WorkflowState.SEND_FAILED

    def _require_state(self, required: WorkflowState) -> None:
        if self._state is not required:
            raise InvalidTransitionError(
                f"Transition requires {required.value}; current state is {self._state.value}"
            )
