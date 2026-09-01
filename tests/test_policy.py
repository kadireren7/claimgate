from __future__ import annotations

from collections.abc import Sequence

from claimgate.domain import (
    Claim,
    ClaimCategory,
    DeterministicPolicyEngine,
    EvidenceSource,
    PolicyOutcome,
    VerificationResult,
    VerificationSnapshot,
    VerificationStatus,
    evidence_sha256,
    pdf_sha256,
)


def snapshot(
    pdf: bytes,
    evidence: Sequence[EvidenceSource],
    results: tuple[VerificationResult, ...],
    *,
    succeeded: bool = True,
) -> VerificationSnapshot:
    return VerificationSnapshot(
        pdf_sha256=pdf_sha256(pdf),
        evidence_sha256=evidence_sha256(evidence),
        results=results,
        succeeded=succeeded,
    )


def blocker_codes(decision) -> set[str]:
    return {blocker.code for blocker in decision.blockers}


def test_conflicting_critical_claim_blocks(agreement_pdf, agreement_evidence) -> None:
    claim = Claim("money", "The price is USD 700", category=ClaimCategory.MONEY)
    verification = VerificationResult(
        claim_id="money",
        status=VerificationStatus.CONFLICTING,
        evidence_id="agreement-source",
        quotation="Price: USD 500",
    )

    decision = DeterministicPolicyEngine().evaluate(
        claims=(claim,),
        evidence=agreement_evidence,
        verification=snapshot(agreement_pdf, agreement_evidence, (verification,)),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "CRITICAL_CLAIM_CONFLICTING" in blocker_codes(decision)


def test_unsupported_critical_claim_blocks(agreement_pdf, agreement_evidence) -> None:
    claim = Claim("money", "The price is USD 700", category=ClaimCategory.MONEY)
    verification = VerificationResult("money", VerificationStatus.UNSUPPORTED)

    decision = DeterministicPolicyEngine().evaluate(
        claims=(claim,),
        evidence=agreement_evidence,
        verification=snapshot(agreement_pdf, agreement_evidence, (verification,)),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "CRITICAL_CLAIM_UNSUPPORTED" in blocker_codes(decision)


def test_uncertain_critical_claim_blocks(agreement_pdf, agreement_evidence) -> None:
    claim = Claim("date", "Delivery is due next quarter", category=ClaimCategory.DATES)
    verification = VerificationResult("date", VerificationStatus.UNCERTAIN)

    decision = DeterministicPolicyEngine().evaluate(
        claims=(claim,),
        evidence=agreement_evidence,
        verification=snapshot(agreement_pdf, agreement_evidence, (verification,)),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "CRITICAL_CLAIM_UNCERTAIN" in blocker_codes(decision)


def test_matching_critical_claims_pass(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    decision = DeterministicPolicyEngine().evaluate(
        claims=critical_claims,
        evidence=agreement_evidence,
        verification=snapshot(
            agreement_pdf,
            agreement_evidence,
            supported_verifications,
        ),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert decision.blockers == ()
    assert decision.binding == (
        pdf_sha256(agreement_pdf),
        evidence_sha256(agreement_evidence),
        "claimgate-policy-v1",
    )


def test_changed_pdf_blocks(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    decision = DeterministicPolicyEngine().evaluate(
        claims=critical_claims,
        evidence=agreement_evidence,
        verification=snapshot(
            agreement_pdf,
            agreement_evidence,
            supported_verifications,
        ),
        current_pdf_sha256=pdf_sha256(agreement_pdf + b" changed"),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "PDF_HASH_CHANGED" in blocker_codes(decision)


def test_changed_evidence_blocks(
    agreement_pdf, agreement_evidence, critical_claims, supported_verifications
) -> None:
    original_verification = snapshot(
        agreement_pdf,
        agreement_evidence,
        supported_verifications,
    )
    changed_evidence = (
        EvidenceSource(
            "agreement-source",
            "Authoritative agreement data",
            agreement_evidence[0].content + " Amended after verification.",
        ),
    )

    decision = DeterministicPolicyEngine().evaluate(
        claims=critical_claims,
        evidence=changed_evidence,
        verification=original_verification,
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "EVIDENCE_HASH_CHANGED" in blocker_codes(decision)


def test_missing_verbatim_quotation_blocks(
    agreement_pdf, agreement_evidence, critical_claims
) -> None:
    result = VerificationResult(
        "money",
        VerificationStatus.SUPPORTED,
        evidence_id="agreement-source",
        quotation="Price: USD 999",
    )

    decision = DeterministicPolicyEngine().evaluate(
        claims=(critical_claims[1],),
        evidence=agreement_evidence,
        verification=snapshot(agreement_pdf, agreement_evidence, (result,)),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "EVIDENCE_QUOTATION_NOT_FOUND" in blocker_codes(decision)


def test_verification_failure_blocks(agreement_pdf, agreement_evidence) -> None:
    decision = DeterministicPolicyEngine().evaluate(
        claims=(),
        evidence=agreement_evidence,
        verification=snapshot(agreement_pdf, agreement_evidence, (), succeeded=False),
        current_pdf_sha256=pdf_sha256(agreement_pdf),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "VERIFICATION_FAILED" in blocker_codes(decision)
