"""Bridges the vendor-neutral action model to the SIGN_DOCUMENT Phase 3 pipeline.

This is the only place a concrete ProposedAction is built from Phase3Result.
The claimgate.actions package itself stays vendor-neutral and has no import of
Phase3Result, DraftDocument, or anything else document/eSign specific.
"""

from __future__ import annotations

from datetime import datetime, timezone

from claimgate.actions import (
    ActionApprovalRecord,
    ActionType,
    ProposedAction,
    create_proposed_action,
)
from claimgate.application.phase3_workflow import Phase3Result


def build_sign_document_action(
    result: Phase3Result,
    *,
    action_id: str | None = None,
    actor: str = "claimgate-demo-agent",
) -> ProposedAction:
    """Build the ProposedAction for a SIGN_DOCUMENT run from its Phase3Result.

    Material parameters are derived from the already-validated extracted claims
    rather than the original DraftDocument, so this function depends only on
    Phase3Result and stays usable from the audit/replay/redteam layers, which
    never carry the original draft.
    """

    claims_by_category = {
        claim.category.value: claim.normalized_value for claim in result.extracted_claims
    }
    target = claims_by_category.get("party_identity", result.workflow.run_id)
    return create_proposed_action(
        action_type=ActionType.SIGN_DOCUMENT,
        description=f"Sign and send {result.pdf_path.name} for {target}",
        actor=actor,
        target=target,
        parameters=claims_by_category,
        artifact_sha256=(result.decision.pdf_sha256,),
        evidence_sha256=result.decision.evidence_sha256,
        baseline_policy_version=result.baseline_decision.policy_version,
        policy_profile_id=result.selected_policy_profile.id,
        policy_profile_sha256=result.selected_policy_profile.profile_hash,
        action_id=action_id or f"run-{result.workflow.run_id}",
    )


def build_action_approval_record(
    action: ProposedAction,
    *,
    approved_by: str,
    approved_at: datetime | None = None,
) -> ActionApprovalRecord:
    return ActionApprovalRecord.approve(
        action,
        approved_by=approved_by,
        approved_at=approved_at or datetime.now(timezone.utc),
    )
