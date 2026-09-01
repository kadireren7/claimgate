"""Fixture-only verification for Phase 2; no semantic inference occurs here."""

from __future__ import annotations

from dataclasses import dataclass

from claimgate.application.models import DraftDocument
from claimgate.domain import (
    Claim,
    ClaimCategory,
    EvidenceSource,
    VerificationResult,
    VerificationSnapshot,
    VerificationStatus,
    evidence_sha256,
)


@dataclass(frozen=True)
class FixtureClaim:
    claim: Claim
    document_phrase: str
    evidence_id: str
    evidence_quotation: str


def build_fixture_bundle(
    draft: DraftDocument,
) -> tuple[tuple[FixtureClaim, ...], tuple[EvidenceSource, ...]]:
    field_values = (
        (
            "party",
            ClaimCategory.PARTY_IDENTITY,
            f"Party name: {draft.party_name}",
        ),
        (
            "money",
            ClaimCategory.MONEY,
            f"Contract amount: {draft.amount_display}",
        ),
        (
            "quantity",
            ClaimCategory.QUANTITY,
            f"Quantity: {draft.quantity}",
        ),
        (
            "date",
            ClaimCategory.DATES,
            f"Delivery date: {draft.delivery_date_display}",
        ),
        (
            "scope",
            ClaimCategory.SCOPE,
            f"Scope: {draft.scope}",
        ),
        (
            "deliverable",
            ClaimCategory.DELIVERABLES,
            f"Deliverable: {draft.deliverable}",
        ),
    )
    evidence_id = "phase2-authoritative-source"
    evidence_content = "\n".join(value for _, _, value in field_values)
    evidence = (
        EvidenceSource(
            source_id=evidence_id,
            title="Phase 2 authoritative fixture",
            content=evidence_content,
        ),
    )
    fixtures = tuple(
        FixtureClaim(
            claim=Claim(claim_id=claim_id, text=value, category=category),
            document_phrase=value,
            evidence_id=evidence_id,
            evidence_quotation=value,
        )
        for claim_id, category, value in field_values
    )
    return fixtures, evidence


class FixtureVerifier:
    """Confirm fixed phrases exist in extracted text and their fixture evidence."""

    def verify(
        self,
        *,
        fixtures: tuple[FixtureClaim, ...],
        evidence: tuple[EvidenceSource, ...],
        extracted_text: str,
        verified_pdf_sha256: str,
    ) -> VerificationSnapshot:
        normalized_document = self._normalize(extracted_text)
        evidence_by_id = {source.source_id: source for source in evidence}
        results: list[VerificationResult] = []

        for fixture in fixtures:
            source = evidence_by_id.get(fixture.evidence_id)
            phrase_is_in_pdf = self._normalize(fixture.document_phrase) in normalized_document
            quote_is_in_evidence = (
                source is not None and fixture.evidence_quotation in source.content
            )
            if phrase_is_in_pdf and quote_is_in_evidence:
                results.append(
                    VerificationResult(
                        claim_id=fixture.claim.claim_id,
                        status=VerificationStatus.SUPPORTED,
                        evidence_id=fixture.evidence_id,
                        quotation=fixture.evidence_quotation,
                    )
                )
            else:
                missing_location = "PDF text" if not phrase_is_in_pdf else "fixture evidence"
                results.append(
                    VerificationResult(
                        claim_id=fixture.claim.claim_id,
                        status=VerificationStatus.FAILED,
                        evidence_id=fixture.evidence_id,
                        quotation=fixture.evidence_quotation,
                        notes=f"Expected fixed phrase was not found in {missing_location}",
                    )
                )

        succeeded = all(result.status is VerificationStatus.SUPPORTED for result in results)
        return VerificationSnapshot(
            pdf_sha256=verified_pdf_sha256,
            evidence_sha256=evidence_sha256(evidence),
            results=tuple(results),
            succeeded=succeeded,
            failure_reason=None if succeeded else "Fixture verification failed",
        )

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.split())

