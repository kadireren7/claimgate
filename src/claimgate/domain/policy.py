"""Pure, deterministic, fail-closed ClaimGate policy engine."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from claimgate.domain.hashing import evidence_sha256
from claimgate.domain.models import (
    Claim,
    EvidenceSource,
    PolicyBlocker,
    PolicyDecision,
    PolicyOutcome,
    VerificationResult,
    VerificationSnapshot,
    VerificationStatus,
    validate_sha256,
)

POLICY_VERSION = "claimgate-policy-v1"


class DeterministicPolicyEngine:
    """Evaluate already-extracted claims without performing semantic inference."""

    version = POLICY_VERSION

    def evaluate(
        self,
        *,
        claims: Sequence[Claim],
        evidence: Sequence[EvidenceSource],
        verification: VerificationSnapshot,
        current_pdf_sha256: str,
    ) -> PolicyDecision:
        validate_sha256(current_pdf_sha256, "current_pdf_sha256")
        current_evidence_sha256 = evidence_sha256(evidence)
        blockers: list[PolicyBlocker] = []

        if not verification.succeeded:
            blockers.append(
                PolicyBlocker(
                    code="VERIFICATION_FAILED",
                    message=verification.failure_reason or "Verification did not complete",
                )
            )
        if verification.pdf_sha256 != current_pdf_sha256:
            blockers.append(
                PolicyBlocker(
                    code="PDF_HASH_CHANGED",
                    message="The current PDF differs from the PDF that was verified",
                )
            )
        if verification.evidence_sha256 != current_evidence_sha256:
            blockers.append(
                PolicyBlocker(
                    code="EVIDENCE_HASH_CHANGED",
                    message="The evidence bundle changed after verification",
                )
            )

        claim_counts = Counter(claim.claim_id for claim in claims)
        evidence_counts = Counter(source.source_id for source in evidence)
        duplicate_claim_ids = (
            identifier for identifier, count in claim_counts.items() if count > 1
        )
        for claim_id in sorted(duplicate_claim_ids):
            blockers.append(
                PolicyBlocker(
                    code="DUPLICATE_CLAIM_ID",
                    message=f"Claim ID {claim_id!r} is not unique",
                    claim_id=claim_id,
                )
            )
        for evidence_id in sorted(
            identifier for identifier, count in evidence_counts.items() if count > 1
        ):
            blockers.append(
                PolicyBlocker(
                    code="DUPLICATE_EVIDENCE_ID",
                    message=f"Evidence ID {evidence_id!r} is not unique",
                    evidence_id=evidence_id,
                )
            )

        claims_by_id = {claim.claim_id: claim for claim in claims}
        evidence_by_id = {source.source_id: source for source in evidence}
        results_by_claim: dict[str, VerificationResult] = {}

        for result in sorted(verification.results, key=lambda item: item.claim_id):
            if result.claim_id not in claims_by_id:
                blockers.append(
                    PolicyBlocker(
                        code="UNKNOWN_VERIFICATION_CLAIM",
                        message="Verification refers to an unknown claim",
                        claim_id=result.claim_id,
                    )
                )
                continue
            if result.claim_id in results_by_claim:
                blockers.append(
                    PolicyBlocker(
                        code="DUPLICATE_VERIFICATION",
                        message="Claim has more than one verification result",
                        claim_id=result.claim_id,
                    )
                )
                continue
            results_by_claim[result.claim_id] = result

            if result.status is VerificationStatus.FAILED:
                blockers.append(
                    PolicyBlocker(
                        code="VERIFICATION_FAILED",
                        message=result.notes or "Claim verification failed",
                        claim_id=result.claim_id,
                    )
                )
            self._validate_quotation(result, evidence_by_id, blockers)

        for claim in sorted(claims, key=lambda item: item.claim_id):
            if not claim.is_critical:
                continue
            result = results_by_claim.get(claim.claim_id)
            if result is None:
                blockers.append(
                    PolicyBlocker(
                        code="MISSING_CRITICAL_VERIFICATION",
                        message="Critical claim has no verification result",
                        claim_id=claim.claim_id,
                    )
                )
                continue
            if result.status in {
                VerificationStatus.CONFLICTING,
                VerificationStatus.UNSUPPORTED,
                VerificationStatus.UNCERTAIN,
            }:
                blockers.append(
                    PolicyBlocker(
                        code=f"CRITICAL_CLAIM_{result.status.value}",
                        message=f"Critical claim is {result.status.value.lower()}",
                        claim_id=claim.claim_id,
                        evidence_id=result.evidence_id,
                    )
                )

        outcome = PolicyOutcome.BLOCKED if blockers else PolicyOutcome.READY_FOR_APPROVAL
        return PolicyDecision(
            outcome=outcome,
            pdf_sha256=current_pdf_sha256,
            evidence_sha256=current_evidence_sha256,
            policy_version=self.version,
            blockers=tuple(blockers),
        )

    @staticmethod
    def _validate_quotation(
        result: VerificationResult,
        evidence_by_id: dict[str, EvidenceSource],
        blockers: list[PolicyBlocker],
    ) -> None:
        needs_quotation = result.status in {
            VerificationStatus.SUPPORTED,
            VerificationStatus.CONFLICTING,
        }
        if result.evidence_id is None or result.quotation is None:
            if needs_quotation:
                blockers.append(
                    PolicyBlocker(
                        code="MISSING_EVIDENCE_QUOTATION",
                        message="Supported or conflicting verification lacks an evidence quotation",
                        claim_id=result.claim_id,
                        evidence_id=result.evidence_id,
                    )
                )
            return

        source = evidence_by_id.get(result.evidence_id)
        if source is None:
            blockers.append(
                PolicyBlocker(
                    code="UNKNOWN_EVIDENCE_SOURCE",
                    message="Verification refers to an unknown evidence source",
                    claim_id=result.claim_id,
                    evidence_id=result.evidence_id,
                )
            )
            return
        if result.quotation not in source.content:
            blockers.append(
                PolicyBlocker(
                    code="EVIDENCE_QUOTATION_NOT_FOUND",
                    message="Verification quotation is not present verbatim in its evidence source",
                    claim_id=result.claim_id,
                    evidence_id=result.evidence_id,
                )
            )
