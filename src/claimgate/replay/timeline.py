"""Audit timeline derived only from actual run and Decision Receipt state."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from claimgate.audit import DecisionReceipt, ReceiptESignStatus
from claimgate.domain import WorkflowState
from claimgate.replay.models import AuditEventKind, AuditTimelineEvent


def build_audit_timeline(
    *,
    run_id: str,
    run_created_at: datetime,
    receipts: Sequence[DecisionReceipt],
) -> tuple[AuditTimelineEvent, ...]:
    events = [
        AuditTimelineEvent(
            event_id=f"{run_id}:created",
            kind=AuditEventKind.RUN_CREATED,
            timestamp=run_created_at,
            state=WorkflowState.CREATED,
            detail="Run created; no approval or signing authority was exercised.",
        )
    ]
    approval_seen = False
    previous_public_source_ids: set[str] = set()
    for index, receipt in enumerate(receipts, start=1):
        if receipt.approval.occurred and not approval_seen:
            approval_seen = True
            approved_at = receipt.approval.approved_at
            if approved_at is None:
                raise ValueError("Approved receipt is missing its approval timestamp")
            events.append(
                AuditTimelineEvent(
                    event_id=f"{run_id}:approval",
                    kind=AuditEventKind.HUMAN_APPROVAL,
                    timestamp=approved_at,
                    state=WorkflowState.APPROVED,
                    receipt_sha256=receipt.receipt_sha256,
                    decision=receipt.final_decision,
                    detail="Human approval recorded with exact artifact and policy bindings.",
                )
            )
        if receipt.esign.status is not ReceiptESignStatus.NOT_ATTEMPTED:
            events.append(
                AuditTimelineEvent(
                    event_id=f"{run_id}:esign-attempt:{index}",
                    kind=AuditEventKind.ESIGN_ATTEMPT,
                    timestamp=receipt.created_at,
                    state=WorkflowState.SENDING,
                    receipt_sha256=receipt.receipt_sha256,
                    decision=receipt.final_decision,
                    detail="Backend-only eSign attempt recorded; replay cannot repeat it.",
                )
            )
        public_source_ids = {
            source.source_id for source in receipt.evidence.public_sources
        }
        if receipt.esign.status is not ReceiptESignStatus.NOT_ATTEMPTED:
            receipt_kind = AuditEventKind.SEND_RECEIPT
        elif public_source_ids - previous_public_source_ids:
            receipt_kind = AuditEventKind.PUBLIC_EVIDENCE_REEVALUATION
        else:
            receipt_kind = AuditEventKind.VERIFICATION_RECEIPT
        events.append(
            AuditTimelineEvent(
                event_id=f"{run_id}:receipt:{index}",
                kind=receipt_kind,
                timestamp=receipt.created_at,
                state=receipt.workflow_state,
                receipt_sha256=receipt.receipt_sha256,
                decision=receipt.final_decision,
                blocker_codes=receipt.blocker_codes,
                detail=(
                    "Verification decision receipt issued."
                    if receipt_kind is AuditEventKind.VERIFICATION_RECEIPT
                    else (
                        "Public evidence snapshot validated and deterministic policy reevaluated."
                        if receipt_kind
                        is AuditEventKind.PUBLIC_EVIDENCE_REEVALUATION
                        else f"Send outcome receipt issued: {receipt.esign.status.value}."
                    )
                ),
            )
        )
        previous_public_source_ids = public_source_ids
    return tuple(events)
