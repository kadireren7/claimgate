"""Canonical receipt issuance and deterministic verification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from claimgate.actions import ExecutionCapability, ProposedAction, action_sha256, get_capability
from claimgate.application import Phase3Result, ProfileApprovalRecord, build_sign_document_action
from claimgate.audit.models import (
    DecisionReceipt,
    ReceiptApprovalSummary,
    ReceiptClaimSummary,
    ReceiptDecision,
    ReceiptESignStatus,
    ReceiptESignSummary,
    ReceiptEvidenceSummary,
    ReceiptPolicySummary,
    ReceiptPublicEvidenceSummary,
    ReceiptVerificationResult,
    ReceiptVerificationStatus,
)
from claimgate.domain import (
    POLICY_VERSION,
    EvidenceSource,
    PolicyOutcome,
    VerificationStatus,
    evidence_sha256,
    pdf_sha256,
)
from claimgate.policy_profiles import PolicyProfile
from claimgate.semantic import SemanticVerificationStatus
from claimgate.semantic.evidence import EvidenceDocument


def canonical_receipt_payload_json(receipt: DecisionReceipt) -> str:
    """Canonical protected payload; excludes only its self-referential hash field."""

    return json.dumps(
        receipt.model_dump(mode="json", exclude={"receipt_sha256"}),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def canonical_receipt_json(receipt: DecisionReceipt) -> str:
    """Canonical authoritative JSON envelope including its integrity hash."""

    return json.dumps(
        receipt.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def compute_receipt_sha256(receipt: DecisionReceipt) -> str:
    return hashlib.sha256(
        canonical_receipt_payload_json(receipt).encode("utf-8")
    ).hexdigest()


def issue_decision_receipt(
    *,
    result: Phase3Result,
    previous_receipt_sha256: str | None = None,
    created_at: datetime | None = None,
    approval: ProfileApprovalRecord | None = None,
    esign_status: ReceiptESignStatus = ReceiptESignStatus.NOT_ATTEMPTED,
    foxit_identifier: str | None = None,
    action: ProposedAction | None = None,
    execution_capability: ExecutionCapability | None = None,
) -> DecisionReceipt:
    proposed_action = action or build_sign_document_action(result)
    capability = execution_capability or get_capability(proposed_action.action_type)
    verification_by_claim = {
        item.claim_id: item for item in result.verification.results
    }
    supports: dict[str, set[str]] = {}
    conflicts: dict[str, set[str]] = {}
    for comparison in result.semantic_comparisons:
        if comparison.evidence_id is None:
            continue
        if comparison.status is SemanticVerificationStatus.SUPPORTED:
            supports.setdefault(comparison.claim_id, set()).add(comparison.evidence_id)
        elif comparison.status is SemanticVerificationStatus.CONFLICTING:
            conflicts.setdefault(comparison.claim_id, set()).add(comparison.evidence_id)

    claims = tuple(
        ReceiptClaimSummary(
            claim_id=claim.claim_id,
            category=claim.category,
            normalized_value=claim.normalized_value,
            critical=claim.critical,
            verification_status=(
                verification_by_claim[claim.claim_id].status
                if claim.claim_id in verification_by_claim
                else VerificationStatus.FAILED
            ),
            supporting_source_ids=tuple(supports.get(claim.claim_id, set())),
            conflicting_source_ids=tuple(conflicts.get(claim.claim_id, set())),
        )
        for claim in result.extracted_claims
    )
    approval_summary = (
        ReceiptApprovalSummary(occurred=False)
        if approval is None
        else ReceiptApprovalSummary(
            occurred=True,
            approved_at=approval.baseline_approval.approved_at,
            pdf_sha256=approval.baseline_approval.pdf_sha256,
            evidence_sha256=approval.baseline_approval.evidence_sha256,
            baseline_policy_version=approval.baseline_approval.policy_version,
            policy_profile_id=approval.policy_profile_id,
            policy_profile_sha256=approval.policy_profile_hash,
        )
    )
    unsigned = DecisionReceipt(
        run_id=result.workflow.run_id,
        created_at=created_at or datetime.now(timezone.utc),
        workflow_state=result.workflow.state,
        final_decision=(
            ReceiptDecision.PASS
            if result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
            else ReceiptDecision.BLOCKED
        ),
        blocker_codes=tuple(blocker.code for blocker in result.decision.blockers),
        pdf_sha256=result.decision.pdf_sha256,
        pdf_filename=result.pdf_path.name,
        evidence=ReceiptEvidenceSummary(
            evidence_sha256=result.decision.evidence_sha256,
            source_ids=tuple(source.source_id for source in result.evidence),
            public_sources=receipt_public_evidence(result.evidence_documents),
        ),
        policy=ReceiptPolicySummary(
            baseline_policy_version=result.baseline_decision.policy_version,
            policy_profile_id=result.selected_policy_profile.id,
            policy_profile_sha256=result.selected_policy_profile.profile_hash,
        ),
        claims=claims,
        approval=approval_summary,
        esign=ReceiptESignSummary(
            status=esign_status,
            foxit_identifier=foxit_identifier,
        ),
        action_id=proposed_action.action_id,
        action_type=proposed_action.action_type,
        action_sha256=action_sha256(proposed_action),
        action_target=proposed_action.target,
        action_risk=proposed_action.risk,
        execution_capability=capability,
        previous_receipt_sha256=previous_receipt_sha256,
        receipt_sha256="0" * 64,
    )
    return unsigned.model_copy(
        update={"receipt_sha256": compute_receipt_sha256(unsigned)}
    )


def receipt_public_evidence(
    evidence_documents: tuple[EvidenceDocument, ...],
) -> tuple[ReceiptPublicEvidenceSummary, ...]:
    summaries = []
    for document in evidence_documents:
        provenance = document.provenance
        if provenance is None:
            continue
        summaries.append(
            ReceiptPublicEvidenceSummary(
                source_id=document.source.source_id,
                provider=provenance.provider,
                source_url=provenance.source_url,
                domain=provenance.domain,
                retrieved_at=provenance.retrieved_at,
                query=provenance.query,
                authority=document.authority,
                source_type=provenance.source_type,
            )
        )
    return tuple(sorted(summaries, key=lambda item: item.source_id))


@dataclass(frozen=True)
class ReceiptVerificationContext:
    pdf_path: Path
    evidence: tuple[EvidenceSource, ...]
    policy_profile: PolicyProfile
    approval: ProfileApprovalRecord | None
    expected_previous_receipt_sha256: str | None
    evidence_documents: tuple[EvidenceDocument, ...] = ()


def verify_receipt(
    receipt: DecisionReceipt,
    context: ReceiptVerificationContext,
) -> ReceiptVerificationResult:
    blockers: list[str] = []
    computed_hash = compute_receipt_sha256(receipt)
    if computed_hash != receipt.receipt_sha256:
        blockers.append("RECEIPT_INTEGRITY_FAILURE")
    if (
        not context.pdf_path.is_file()
        or pdf_sha256(context.pdf_path.read_bytes()) != receipt.pdf_sha256
    ):
        blockers.append("RECEIPT_PDF_HASH_MISMATCH")
    if context.pdf_path.name != receipt.pdf_filename:
        blockers.append("RECEIPT_PDF_FILENAME_MISMATCH")
    if evidence_sha256(context.evidence) != receipt.evidence.evidence_sha256:
        blockers.append("RECEIPT_EVIDENCE_HASH_MISMATCH")
    if (
        tuple(sorted(source.source_id for source in context.evidence))
        != receipt.evidence.source_ids
    ):
        blockers.append("RECEIPT_EVIDENCE_SOURCE_MISMATCH")
    if receipt_public_evidence(context.evidence_documents) != receipt.evidence.public_sources:
        blockers.append("RECEIPT_PUBLIC_EVIDENCE_PROVENANCE_MISMATCH")
    if receipt.policy.baseline_policy_version != POLICY_VERSION:
        blockers.append("RECEIPT_BASELINE_POLICY_MISMATCH")
    if context.policy_profile.id != receipt.policy.policy_profile_id:
        blockers.append("RECEIPT_POLICY_PROFILE_MISMATCH")
    if context.policy_profile.profile_hash != receipt.policy.policy_profile_sha256:
        blockers.append("RECEIPT_POLICY_PROFILE_HASH_MISMATCH")
    if receipt.previous_receipt_sha256 != context.expected_previous_receipt_sha256:
        blockers.append("RECEIPT_CHAIN_LINK_MISMATCH")
    _verify_approval(receipt, context.approval, blockers)
    return ReceiptVerificationResult(
        status=(
            ReceiptVerificationStatus.TAMPERED
            if blockers
            else ReceiptVerificationStatus.VERIFIED
        ),
        receipt_sha256=receipt.receipt_sha256,
        computed_receipt_sha256=computed_hash,
        blocker_codes=tuple(blockers),
    )


def _verify_approval(
    receipt: DecisionReceipt,
    approval: ProfileApprovalRecord | None,
    blockers: list[str],
) -> None:
    summary = receipt.approval
    if not summary.occurred:
        if approval is not None:
            blockers.append("RECEIPT_APPROVAL_STATE_MISMATCH")
        return
    if approval is None:
        blockers.append("RECEIPT_APPROVAL_MISSING")
        return
    expected = (
        approval.baseline_approval.pdf_sha256,
        approval.baseline_approval.evidence_sha256,
        approval.baseline_approval.policy_version,
        approval.policy_profile_id,
        approval.policy_profile_hash,
    )
    observed = (
        summary.pdf_sha256,
        summary.evidence_sha256,
        summary.baseline_policy_version,
        summary.policy_profile_id,
        summary.policy_profile_sha256,
    )
    if expected != observed:
        blockers.append("RECEIPT_APPROVAL_BINDING_MISMATCH")
    if summary.approved_at != approval.baseline_approval.approved_at:
        blockers.append("RECEIPT_APPROVAL_TIMESTAMP_MISMATCH")
    if observed != (
        receipt.pdf_sha256,
        receipt.evidence.evidence_sha256,
        receipt.policy.baseline_policy_version,
        receipt.policy.policy_profile_id,
        receipt.policy.policy_profile_sha256,
    ):
        blockers.append("RECEIPT_APPROVAL_ARTIFACT_MISMATCH")
