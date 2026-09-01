from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from claimgate.application import DraftDocument
from claimgate.domain import (
    Claim,
    ClaimCategory,
    EvidenceSource,
    VerificationResult,
    VerificationStatus,
)

QUOTATIONS = {
    "party": "Supplier: Acme Corp",
    "money": "Price: USD 500",
    "quantity": "Quantity: 10 widgets",
    "date": "Delivery date: 2026-09-01",
    "deliverable": "Deliverable: ten blue widgets",
    "scope": "Scope: Istanbul pilot only",
    "obligation": "Obligation: Acme Corp must deliver the widgets",
}


@pytest.fixture
def agreement_pdf() -> bytes:
    return b"%PDF-1.4\nClaimGate policy fixture"


@pytest.fixture
def agreement_evidence() -> tuple[EvidenceSource, ...]:
    return (
        EvidenceSource(
            source_id="agreement-source",
            title="Authoritative agreement data",
            content=(
                "Supplier: Acme Corp. Price: USD 500. Quantity: 10 widgets. "
                "Delivery date: 2026-09-01. Deliverable: ten blue widgets. "
                "Scope: Istanbul pilot only. "
                "Obligation: Acme Corp must deliver the widgets."
            ),
        ),
    )


@pytest.fixture
def critical_claims() -> tuple[Claim, ...]:
    return (
        Claim("party", "The supplier is Acme Corp", ClaimCategory.PARTY_IDENTITY),
        Claim("money", "The price is USD 500", ClaimCategory.MONEY),
        Claim("quantity", "The quantity is 10 widgets", ClaimCategory.QUANTITY),
        Claim("date", "Delivery is due on 2026-09-01", ClaimCategory.DATES),
        Claim("deliverable", "Ten blue widgets will be delivered", ClaimCategory.DELIVERABLES),
        Claim("scope", "The agreement covers the Istanbul pilot", ClaimCategory.SCOPE),
        Claim("obligation", "Acme must deliver the widgets", ClaimCategory.OBLIGATIONS),
    )


@pytest.fixture
def supported_verifications(critical_claims) -> tuple[VerificationResult, ...]:
    return tuple(
        VerificationResult(
            claim_id=claim.claim_id,
            status=VerificationStatus.SUPPORTED,
            evidence_id="agreement-source",
            quotation=QUOTATIONS[claim.claim_id],
        )
        for claim in critical_claims
    )


@pytest.fixture
def phase2_draft() -> DraftDocument:
    return DraftDocument(
        party_name="Acme Corporation",
        contract_amount=Decimal("12500.00"),
        quantity=250,
        delivery_date=date(2026, 9, 30),
        scope="Istanbul pilot deployment",
        deliverable="250 configured devices",
    )
