"""Deterministic semantic responses and evidence for the two-minute demo."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from claimgate.application.models import DraftDocument
from claimgate.domain import ClaimCategory
from claimgate.domain.models import CRITICAL_CLAIM_CATEGORIES
from claimgate.evidence_graph import EvidenceAuthority
from claimgate.semantic import (
    EvidenceDocument,
    EvidenceIngestor,
    ScriptedSemanticProvider,
    StructuredRequest,
)


class Phase3Preset(str, Enum):
    PASS = "pass"
    BLOCK = "block"
    EVIDENCE_GRAPH = "evidence_graph"
    PUBLIC_CLAIM = "public_claim"


@dataclass(frozen=True)
class Phase3PresetBundle:
    evidence_documents: tuple[EvidenceDocument, ...]
    scripted_provider: ScriptedSemanticProvider


def build_phase3_preset(
    draft: DraftDocument, preset: Phase3Preset
) -> Phase3PresetBundle:
    authority_amount = (
        "USD 15,000.00" if preset is Phase3Preset.BLOCK else draft.amount_display
    )
    authority_lines = {
        "party": f"Party name: {draft.party_name}",
        "money": f"Contract amount: {authority_amount}",
        "quantity": f"Quantity: {draft.quantity}",
    }
    delivery_lines = {
        "date": f"Delivery date: {draft.delivery_date_display}",
        "scope": f"Scope: {draft.scope}",
        "deliverable": f"Deliverable: {draft.deliverable}",
    }
    evidence_documents: tuple[EvidenceDocument, ...] = (
        EvidenceIngestor.plain_text(
            source_id="commercial-authority",
            title="Approved commercial terms",
            text="\n".join(authority_lines.values()),
            authority=EvidenceAuthority.AUTHORITATIVE_INTERNAL,
        ),
        EvidenceIngestor.pdf_derived_text(
            source_id="delivery-authority-pdf",
            title="Foxit-extracted statement of work fixture",
            extracted_text="\n".join(delivery_lines.values()),
            authority=EvidenceAuthority.AUTHORITATIVE_INTERNAL,
        ),
    )
    purchase_order_line = f"Purchase order amount: {draft.amount_display}"
    conflicting_email_line = "Requested contract amount: USD 15,000.00"
    if preset is Phase3Preset.EVIDENCE_GRAPH:
        evidence_documents += (
            EvidenceIngestor.pdf_derived_text(
                source_id="purchase-order-pdf",
                title="Foxit-extracted purchase order",
                extracted_text=purchase_order_line,
                authority=EvidenceAuthority.VERIFIED_EXTERNAL,
            ),
            EvidenceIngestor.plain_text(
                source_id="customer-email",
                title="Customer change-request email",
                text=conflicting_email_line,
                authority=EvidenceAuthority.UNVERIFIED_EXTERNAL,
            ),
        )

    specs = (
        (
            "party",
            ClaimCategory.PARTY_IDENTITY,
            draft.party_name,
            f"Party name: {draft.party_name}",
        ),
        (
            "money",
            ClaimCategory.MONEY,
            f"{draft.currency.upper()} {draft.contract_amount:.2f}",
            f"Contract amount: {draft.amount_display}",
        ),
        (
            "quantity",
            ClaimCategory.QUANTITY,
            str(draft.quantity),
            f"Quantity: {draft.quantity}",
        ),
        (
            "date",
            ClaimCategory.DATES,
            draft.delivery_date.isoformat(),
            f"Delivery date: {draft.delivery_date_display}",
        ),
        ("scope", ClaimCategory.SCOPE, draft.scope, f"Scope: {draft.scope}"),
        (
            "deliverable",
            ClaimCategory.DELIVERABLES,
            draft.deliverable,
            f"Deliverable: {draft.deliverable}",
        ),
    )
    if draft.public_fact is not None:
        specs += (
            (
                "certification",
                ClaimCategory.OTHER,
                draft.public_fact,
                f"Public status: {draft.public_fact}",
            ),
        )

    def extraction_response(request: StructuredRequest) -> object:
        pdf_text = str(request.untrusted_data["pdf_text"])
        return {
            "complete": True,
            "claims": [
                {
                    "claim_id": claim_id,
                    "category": category.value,
                    "normalized_value": normalized_value,
                    "source_text": _verbatim_span(pdf_text, expected_text),
                    "critical": category in CRITICAL_CLAIM_CATEGORIES,
                }
                for claim_id, category, normalized_value, expected_text in specs
            ],
        }

    def comparison_response(request: StructuredRequest) -> object:
        results = []
        for claim in request.untrusted_data["claims"]:
            claim_id = claim["claim_id"]
            if claim_id == "certification":
                results.append(
                    {
                        "claim_id": claim_id,
                        "status": "UNSUPPORTED",
                        "evidence_id": None,
                        "quotation": None,
                        "notes": "No supplied evidence covers the public certification claim",
                    }
                )
                continue
            source_id = (
                "commercial-authority"
                if claim_id in authority_lines
                else "delivery-authority-pdf"
            )
            quotation = (
                authority_lines[claim_id]
                if claim_id in authority_lines
                else delivery_lines[claim_id]
            )
            is_conflict = preset is Phase3Preset.BLOCK and claim_id == "money"
            results.append(
                {
                    "claim_id": claim_id,
                    "status": "CONFLICTING" if is_conflict else "SUPPORTED",
                    "evidence_id": source_id,
                    "quotation": quotation,
                    "notes": (
                        "Authoritative amount differs from the PDF"
                        if is_conflict
                        else "Claim matches authoritative evidence"
                    ),
                }
            )
            if preset is Phase3Preset.EVIDENCE_GRAPH and claim_id == "money":
                results.extend(
                    (
                        {
                            "claim_id": "money",
                            "status": "SUPPORTED",
                            "evidence_id": "purchase-order-pdf",
                            "quotation": purchase_order_line,
                            "notes": "Purchase order matches the document amount",
                        },
                        {
                            "claim_id": "money",
                            "status": "CONFLICTING",
                            "evidence_id": "customer-email",
                            "quotation": conflicting_email_line,
                            "notes": "Customer email contains a different amount",
                        },
                    )
                )
        return {"complete": True, "results": results}

    return Phase3PresetBundle(
        evidence_documents=evidence_documents,
        scripted_provider=ScriptedSemanticProvider(
            [extraction_response, comparison_response]
        ),
    )


def _verbatim_span(text: str, expected: str) -> str:
    pattern = r"\s+".join(re.escape(token) for token in expected.split())
    match = re.search(pattern, text)
    return match.group(0) if match else expected
