from __future__ import annotations

from datetime import UTC, datetime

import pytest

from claimgate.domain import (
    ApprovalRecord,
    DeterministicPolicyEngine,
    InvalidTransitionError,
    VerificationSnapshot,
    WorkflowRun,
    WorkflowState,
    evidence_sha256,
    pdf_sha256,
)


def prepare_run(agreement_pdf, agreement_evidence, critical_claims, supported_verifications):
    pdf_hash = pdf_sha256(agreement_pdf)
    evidence_hash = evidence_sha256(agreement_evidence)
    verification = VerificationSnapshot(
        pdf_sha256=pdf_hash,
        evidence_sha256=evidence_hash,
        results=supported_verifications,
    )
    decision = DeterministicPolicyEngine().evaluate(
        claims=critical_claims,
        evidence=agreement_evidence,
        verification=verification,
        current_pdf_sha256=pdf_hash,
    )
    run = WorkflowRun("run-1")
    run.start_generation()
    run.start_verification(pdf_sha256=pdf_hash, evidence_sha256=evidence_hash)
    return run, decision


def test_blocked_run_cannot_transition_to_approval(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    run, passing_decision = prepare_run(
        agreement_pdf, agreement_evidence, critical_claims, supported_verifications
    )
    blocked_decision = DeterministicPolicyEngine().evaluate(
        claims=critical_claims,
        evidence=agreement_evidence,
        verification=VerificationSnapshot(
            pdf_sha256=pdf_sha256(agreement_pdf),
            evidence_sha256=evidence_sha256(agreement_evidence),
            results=(),
            succeeded=False,
            failure_reason="Verifier unavailable",
        ),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )
    run.apply_policy(blocked_decision)
    approval = ApprovalRecord.for_decision(
        approved_by="human@example.com",
        approved_at=datetime(2026, 8, 19, tzinfo=UTC),
        decision=passing_decision,
    )

    with pytest.raises(InvalidTransitionError, match="READY_FOR_APPROVAL"):
        run.approve(approval)
    assert run.state is WorkflowState.BLOCKED


def test_no_path_can_send_without_explicit_approval(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    run, decision = prepare_run(
        agreement_pdf, agreement_evidence, critical_claims, supported_verifications
    )
    run.apply_policy(decision)
    assert run.state is WorkflowState.READY_FOR_APPROVAL

    with pytest.raises(InvalidTransitionError, match="APPROVED"):
        run.start_sending()

    approval = ApprovalRecord.for_decision(
        approved_by="human@example.com",
        approved_at=datetime(2026, 8, 19, tzinfo=UTC),
        decision=decision,
    )
    run.approve(approval)
    assert run.state is WorkflowState.APPROVED
    assert approval.binding == decision.binding

    run.start_sending()
    assert run.state is WorkflowState.SENDING
    run.mark_sent()
    assert run.state is WorkflowState.SENT


@pytest.mark.parametrize("changed_field", ["pdf", "evidence", "policy"])
def test_approval_with_wrong_binding_is_rejected(
    agreement_pdf,
    agreement_evidence,
    critical_claims,
    supported_verifications,
    changed_field,
) -> None:
    run, decision = prepare_run(
        agreement_pdf, agreement_evidence, critical_claims, supported_verifications
    )
    run.apply_policy(decision)
    wrong_approval = ApprovalRecord(
        approved_by="human@example.com",
        approved_at=datetime(2026, 8, 19, tzinfo=UTC),
        pdf_sha256=(
            pdf_sha256(agreement_pdf + b" changed")
            if changed_field == "pdf"
            else decision.pdf_sha256
        ),
        evidence_sha256=(
            evidence_sha256(agreement_evidence + agreement_evidence)
            if changed_field == "evidence"
            else decision.evidence_sha256
        ),
        policy_version=(
            "different-policy" if changed_field == "policy" else decision.policy_version
        ),
    )

    with pytest.raises(InvalidTransitionError, match="not bound"):
        run.approve(wrong_approval)
    assert run.state is WorkflowState.READY_FOR_APPROVAL


def test_send_failure_is_terminal_for_phase_one(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    run, decision = prepare_run(
        agreement_pdf, agreement_evidence, critical_claims, supported_verifications
    )
    run.apply_policy(decision)
    run.approve(
        ApprovalRecord.for_decision(
            approved_by="human@example.com",
            approved_at=datetime(2026, 8, 19, tzinfo=UTC),
            decision=decision,
        )
    )
    run.start_sending()
    run.mark_send_failed()

    assert run.state is WorkflowState.SEND_FAILED
    with pytest.raises(InvalidTransitionError):
        run.start_sending()
