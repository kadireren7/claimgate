"""Human-only approval and eSign handoff outside every agent/provider boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from claimgate.application.phase3_workflow import Phase3Result
from claimgate.domain import (
    POLICY_VERSION,
    ApprovalRecord,
    PolicyOutcome,
    WorkflowState,
    evidence_sha256,
    pdf_sha256,
)
from claimgate.domain.models import validate_sha256
from claimgate.integrations.foxit_esign import ESignSendResult, Signer
from claimgate.policy_profiles import (
    PolicyEvaluationContext,
    PolicyProfileEvaluator,
    ProfilePolicyOutcome,
)


class ApprovalBoundaryError(RuntimeError):
    """Raised before eSign when confirmation, state, or a binding is invalid."""


class ESignSender(Protocol):
    def send_pdf_for_signature(
        self, pdf_path: Path, signer: Signer
    ) -> ESignSendResult: ...


@dataclass(frozen=True)
class ProfileApprovalRecord:
    """Application approval binding layered over the Phase 1 approval record."""

    baseline_approval: ApprovalRecord
    policy_profile_id: str
    policy_profile_hash: str

    def __post_init__(self) -> None:
        if not self.policy_profile_id.strip():
            raise ValueError("policy_profile_id must not be empty")
        validate_sha256(self.policy_profile_hash, "approval policy_profile_hash")

    @property
    def binding(self) -> tuple[str, str, str, str, str]:
        return (
            *self.baseline_approval.binding,
            self.policy_profile_id,
            self.policy_profile_hash,
        )


@dataclass(frozen=True)
class ApprovalSendOutcome:
    state: WorkflowState
    approval: ProfileApprovalRecord
    folder_id: str | None = None
    error: str | None = None


class ApprovalSendService:
    """Create a bound approval, recheck it, and make exactly one send call."""

    def __init__(self, sender: ESignSender) -> None:
        self._sender = sender

    def approve_and_send(
        self,
        *,
        result: Phase3Result,
        signer: Signer,
        approved_by: str,
        confirmed: bool,
        approval: ProfileApprovalRecord | ApprovalRecord | None = None,
    ) -> ApprovalSendOutcome:
        if not confirmed:
            raise ApprovalBoundaryError("Explicit human confirmation is required")
        if result.decision.outcome is not PolicyOutcome.READY_FOR_APPROVAL:
            raise ApprovalBoundaryError("Blocked policy decisions cannot be approved")
        if result.workflow.state is not WorkflowState.READY_FOR_APPROVAL:
            raise ApprovalBoundaryError(
                f"Run cannot be approved from state {result.workflow.state.value}"
            )
        if result.profile_decision.outcome is not ProfilePolicyOutcome.PASS:
            raise ApprovalBoundaryError("Selected policy profile does not permit approval")

        self._require_current_binding(result)
        if isinstance(approval, ApprovalRecord):
            if approval.binding != result.decision.binding:
                raise ApprovalBoundaryError(
                    "Approval binding is stale or does not match the decision"
                )
            raise ApprovalBoundaryError("Approval binding is stale: policy profile is missing")
        bound_approval = approval or ProfileApprovalRecord(
            baseline_approval=ApprovalRecord.for_decision(
                approved_by=approved_by,
                approved_at=datetime.now(timezone.utc),
                decision=result.decision,
            ),
            policy_profile_id=result.selected_policy_profile.id,
            policy_profile_hash=result.selected_policy_profile.profile_hash,
        )
        if bound_approval.binding != self._expected_approval_binding(result):
            raise ApprovalBoundaryError("Approval binding is stale or does not match the decision")

        result.workflow.approve(bound_approval.baseline_approval)

        # This is intentionally repeated immediately before the irreversible send.
        self._require_current_binding(result, approval=bound_approval)
        result.workflow.start_sending()
        try:
            send_result = self._sender.send_pdf_for_signature(result.pdf_path, signer)
        except Exception:
            result.workflow.mark_send_failed()
            return ApprovalSendOutcome(
                state=WorkflowState.SEND_FAILED,
                approval=bound_approval,
                error="E-signature send failed. The request was not retried.",
            )

        result.workflow.mark_sent()
        return ApprovalSendOutcome(
            state=WorkflowState.SENT,
            approval=bound_approval,
            folder_id=send_result.folder_id,
        )

    @staticmethod
    def _require_current_binding(
        result: Phase3Result, approval: ProfileApprovalRecord | None = None
    ) -> None:
        if result.decision.policy_version != POLICY_VERSION:
            raise ApprovalBoundaryError("Policy version changed after verification")
        if pdf_sha256(result.pdf_path.read_bytes()) != result.decision.pdf_sha256:
            raise ApprovalBoundaryError("PDF changed after verification")
        if evidence_sha256(result.evidence) != result.decision.evidence_sha256:
            raise ApprovalBoundaryError("Evidence changed after verification")
        if result.baseline_decision.binding != result.decision.binding:
            raise ApprovalBoundaryError("Baseline decision binding changed after verification")
        profile = result.selected_policy_profile
        if result.profile_decision.profile_id != profile.id:
            raise ApprovalBoundaryError("Policy profile changed after verification")
        if result.profile_decision.profile_hash != profile.profile_hash:
            raise ApprovalBoundaryError("Policy profile contents changed after verification")
        reevaluated = PolicyProfileEvaluator().evaluate(
            PolicyEvaluationContext(
                baseline_decision=result.baseline_decision,
                selected_profile=profile,
                evidence_graph=result.evidence_graph,
            )
        )
        if (
            reevaluated.profile_decision != result.profile_decision
            or reevaluated.final_decision != result.decision
        ):
            raise ApprovalBoundaryError("Policy evaluation changed after verification")
        if (
            approval is not None
            and approval.binding
            != ApprovalSendService._expected_approval_binding(result)
        ):
            raise ApprovalBoundaryError("Approval binding changed before send")

    @staticmethod
    def _expected_approval_binding(
        result: Phase3Result,
    ) -> tuple[str, str, str, str, str]:
        return (
            *result.decision.binding,
            result.selected_policy_profile.id,
            result.selected_policy_profile.profile_hash,
        )
