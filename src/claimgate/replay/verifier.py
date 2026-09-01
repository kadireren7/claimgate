"""Deterministic historical replay using receipts and current artifact observations only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING

from claimgate.actions import ProposedAction
from claimgate.actions import action_sha256 as compute_action_sha256
from claimgate.audit import (
    DecisionReceipt,
    ReceiptApprovalSummary,
    ReceiptESignSummary,
    compute_receipt_sha256,
    receipt_public_evidence,
)
from claimgate.domain import POLICY_VERSION, EvidenceSource, evidence_sha256, pdf_sha256
from claimgate.policy_profiles import PolicyProfile
from claimgate.replay.models import (
    ArtifactSnapshot,
    ReplayCheck,
    ReplayCheckStatus,
    ReplayPreset,
    ReplayRequest,
    ReplayResult,
    ReplayStatus,
)
from claimgate.semantic import EvidenceDocument

if TYPE_CHECKING:
    from claimgate.application import ProfileApprovalRecord


def capture_artifact_snapshot(
    *,
    pdf_path: Path,
    evidence: tuple[EvidenceSource, ...] | None,
    policy_profile: PolicyProfile,
    approval: ProfileApprovalRecord | None,
    esign: ReceiptESignSummary,
    expected_previous_receipt_sha256: str | None,
    action: ProposedAction,
    evidence_documents: tuple[EvidenceDocument, ...] = (),
) -> ArtifactSnapshot:
    pdf_available = pdf_path.is_file()
    evidence_available = evidence is not None
    return ArtifactSnapshot(
        pdf_available=pdf_available,
        pdf_sha256=pdf_sha256(pdf_path.read_bytes()) if pdf_available else None,
        evidence_available=evidence_available,
        evidence_sha256=evidence_sha256(evidence) if evidence is not None else None,
        evidence_source_ids=(
            tuple(source.source_id for source in evidence)
            if evidence is not None
            else ()
        ),
        public_evidence=receipt_public_evidence(evidence_documents),
        action_id=action.action_id,
        action_type=action.action_type,
        action_sha256=compute_action_sha256(action),
        baseline_policy_version=POLICY_VERSION,
        policy_profile_id=policy_profile.id,
        policy_profile_sha256=policy_profile.profile_hash,
        approval=_approval_summary(approval),
        esign=esign,
        expected_previous_receipt_sha256=expected_previous_receipt_sha256,
    )


def apply_replay_preset(
    snapshot: ArtifactSnapshot, preset: ReplayPreset
) -> ArtifactSnapshot:
    """Create a temporary observed-state variation without mutating historical state."""

    if preset is ReplayPreset.CLEAN_REPLAY:
        return snapshot
    if preset is ReplayPreset.PDF_DRIFT:
        return snapshot.model_copy(
            update={"pdf_available": True, "pdf_sha256": _different_hash(snapshot.pdf_sha256)}
        )
    if preset is ReplayPreset.EVIDENCE_DRIFT:
        return snapshot.model_copy(
            update={
                "evidence_available": True,
                "evidence_sha256": _different_hash(snapshot.evidence_sha256),
            }
        )
    if preset is ReplayPreset.POLICY_DRIFT:
        return snapshot.model_copy(
            update={
                "policy_profile_sha256": _different_hash(
                    snapshot.policy_profile_sha256
                )
            }
        )
    if preset is ReplayPreset.BROKEN_CHAIN:
        return snapshot.model_copy(
            update={
                "expected_previous_receipt_sha256": _different_hash(
                    snapshot.expected_previous_receipt_sha256
                )
            }
        )
    if preset is ReplayPreset.ACTION_PARAMETER_DRIFT:
        return snapshot.model_copy(
            update={"action_sha256": _different_hash(snapshot.action_sha256)}
        )
    raise ValueError(f"Unsupported replay preset: {preset}")


class ReplayVerifier:
    """Read-only proof verifier with no provider, workflow, approval, or send dependency."""

    def verify(
        self,
        *,
        request: ReplayRequest,
        receipt: DecisionReceipt,
        snapshot: ArtifactSnapshot,
    ) -> ReplayResult:
        checks = (
            self._check(
                "receipt_selection",
                "Requested receipt",
                request.receipt_sha256,
                receipt.receipt_sha256,
                "REPLAY_RECEIPT_SELECTION_MISMATCH",
                "The server-selected historical receipt matches the replay request.",
                "The replay request does not identify this server-known receipt.",
            ),
            self._check(
                "receipt_integrity",
                "Receipt integrity",
                receipt.receipt_sha256,
                compute_receipt_sha256(receipt),
                "RECEIPT_INTEGRITY_FAILURE",
                "Canonical receipt JSON retains its original integrity hash.",
                "The historical receipt content no longer matches its integrity hash.",
            ),
            self._availability_check(
                "pdf_availability",
                "Historical PDF availability",
                snapshot.pdf_available,
                "PDF_ARTIFACT_MISSING",
                "The bound PDF is available to replay.",
                "The bound historical PDF is no longer available.",
            ),
            self._check(
                "pdf_hash",
                "Historical PDF binding",
                receipt.pdf_sha256,
                snapshot.pdf_sha256 or "MISSING",
                "PDF_HASH_MISMATCH",
                "The current PDF bytes match the historical receipt.",
                "Historical artifact drift detected: current PDF bytes differ.",
            ),
            self._availability_check(
                "evidence_availability",
                "Historical evidence availability",
                snapshot.evidence_available,
                "EVIDENCE_ARTIFACT_MISSING",
                "The bound evidence set is available to replay.",
                "The bound historical evidence set is no longer available.",
            ),
            self._check(
                "evidence_hash",
                "Historical evidence binding",
                receipt.evidence.evidence_sha256,
                snapshot.evidence_sha256 or "MISSING",
                "EVIDENCE_HASH_MISMATCH",
                "Current evidence matches the historical receipt.",
                "Historical evidence drift detected.",
            ),
            self._check(
                "evidence_sources",
                "Evidence source identifiers",
                _joined(receipt.evidence.source_ids),
                _joined(snapshot.evidence_source_ids),
                "EVIDENCE_SOURCE_IDS_MISMATCH",
                "The historical evidence source set is unchanged.",
                "The current evidence source identifiers differ.",
            ),
            self._check(
                "public_evidence_provenance",
                "Public evidence provenance",
                _canonical_public_sources(receipt.evidence.public_sources),
                _canonical_public_sources(snapshot.public_evidence),
                "PUBLIC_EVIDENCE_PROVENANCE_MISMATCH",
                "The historical public evidence snapshot and provenance are unchanged.",
                "Public evidence provenance differs from the historical receipt.",
            ),
            self._check(
                "baseline_policy",
                "Baseline policy version",
                receipt.policy.baseline_policy_version,
                snapshot.baseline_policy_version,
                "BASELINE_POLICY_VERSION_MISMATCH",
                "The baseline policy version matches the historical decision.",
                "The active baseline policy version differs from the receipt.",
            ),
            self._check(
                "policy_profile_id",
                "Policy profile identifier",
                receipt.policy.policy_profile_id,
                snapshot.policy_profile_id,
                "POLICY_PROFILE_ID_MISMATCH",
                "The selected policy profile ID is unchanged.",
                "The selected policy profile ID differs.",
            ),
            self._check(
                "policy_profile_hash",
                "Policy profile contents",
                receipt.policy.policy_profile_sha256,
                snapshot.policy_profile_sha256,
                "POLICY_PROFILE_HASH_MISMATCH",
                "The policy profile contents match their historical hash.",
                "Policy profile contents drifted, even if its ID stayed the same.",
            ),
            self._check(
                "action_binding",
                "Protected action binding",
                receipt.action_sha256,
                snapshot.action_sha256,
                "ACTION_DRIFT",
                "The canonical action hash matches the historical receipt.",
                "A protected action parameter drifted from the historical receipt.",
            ),
            self._check(
                "approval_binding",
                "Human approval binding",
                _canonical_model(receipt.approval),
                _canonical_model(snapshot.approval),
                "APPROVAL_BINDING_MISMATCH",
                "Approval state and artifact/profile bindings match the receipt.",
                "The historical approval binding no longer matches.",
            ),
            self._check(
                "esign_state",
                "Recorded eSign state",
                _canonical_model(receipt.esign),
                _canonical_model(snapshot.esign),
                "ESIGN_STATE_MISMATCH",
                "The recorded eSign outcome matches the historical event.",
                "The observed eSign event state differs from the receipt.",
            ),
            self._check(
                "previous_receipt",
                "Previous receipt chain link",
                receipt.previous_receipt_sha256 or "GENESIS",
                snapshot.expected_previous_receipt_sha256 or "GENESIS",
                "PREVIOUS_RECEIPT_CHAIN_MISMATCH",
                "The receipt points to the expected previous chain entry.",
                "The historical receipt chain link is broken.",
            ),
        )
        blocker_codes = tuple(
            check.blocker_code
            for check in checks
            if check.status is ReplayCheckStatus.FAIL and check.blocker_code is not None
        )
        return ReplayResult(
            run_id=request.run_id,
            receipt_sha256=receipt.receipt_sha256,
            original_final_decision=receipt.final_decision,
            original_workflow_state=receipt.workflow_state,
            status=self._status(blocker_codes),
            checks=checks,
            blocker_codes=blocker_codes,
        )

    @staticmethod
    def _check(
        check_id: str,
        label: str,
        expected: str,
        observed: str,
        blocker_code: str,
        pass_explanation: str,
        fail_explanation: str,
    ) -> ReplayCheck:
        passed = expected == observed
        return ReplayCheck(
            check_id=check_id,
            label=label,
            expected_value=expected,
            observed_value=observed,
            status=ReplayCheckStatus.PASS if passed else ReplayCheckStatus.FAIL,
            blocker_code=None if passed else blocker_code,
            explanation=pass_explanation if passed else fail_explanation,
        )

    @staticmethod
    def _availability_check(
        check_id: str,
        label: str,
        available: bool,
        blocker_code: str,
        pass_explanation: str,
        fail_explanation: str,
    ) -> ReplayCheck:
        return ReplayVerifier._check(
            check_id,
            label,
            "AVAILABLE",
            "AVAILABLE" if available else "MISSING",
            blocker_code,
            pass_explanation,
            fail_explanation,
        )

    @staticmethod
    def _status(blockers: tuple[str, ...]) -> ReplayStatus:
        if not blockers:
            return ReplayStatus.VERIFIED
        if any(
            code in {"RECEIPT_INTEGRITY_FAILURE", "REPLAY_RECEIPT_SELECTION_MISMATCH"}
            for code in blockers
        ):
            return ReplayStatus.INVALID_RECEIPT
        if "PREVIOUS_RECEIPT_CHAIN_MISMATCH" in blockers:
            return ReplayStatus.CHAIN_BROKEN
        if any(code.endswith("ARTIFACT_MISSING") for code in blockers):
            return ReplayStatus.ARTIFACT_MISSING
        return ReplayStatus.DRIFT_DETECTED


def _approval_summary(
    approval: ProfileApprovalRecord | None,
) -> ReceiptApprovalSummary:
    if approval is None:
        return ReceiptApprovalSummary(occurred=False)
    return ReceiptApprovalSummary(
        occurred=True,
        approved_at=approval.baseline_approval.approved_at,
        pdf_sha256=approval.baseline_approval.pdf_sha256,
        evidence_sha256=approval.baseline_approval.evidence_sha256,
        baseline_policy_version=approval.baseline_approval.policy_version,
        policy_profile_id=approval.policy_profile_id,
        policy_profile_sha256=approval.policy_profile_hash,
    )


def _canonical_model(model: ReceiptApprovalSummary | ReceiptESignSummary) -> str:
    return json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _canonical_public_sources(values: tuple[object, ...]) -> str:
    return json.dumps(
        [value.model_dump(mode="json") for value in values],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _joined(values: tuple[str, ...]) -> str:
    return ",".join(values) if values else "NONE"


def _different_hash(current: str | None) -> str:
    return hashlib.sha256(f"replay-drift:{current or 'missing'}".encode()).hexdigest()
