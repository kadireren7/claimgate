from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from claimgate.actions import action_sha256 as compute_action_sha256
from claimgate.application import (
    ApprovalSendService,
    Phase3Preset,
    Phase3Workflow,
    build_phase3_preset,
    build_sign_document_action,
)
from claimgate.audit import (
    RECEIPT_VERSION,
    DecisionReceipt,
    DecisionReceiptPdfGenerator,
    ReceiptDecision,
    ReceiptESignStatus,
    ReceiptESignSummary,
    ReceiptVerificationContext,
    ReceiptVerificationStatus,
    canonical_receipt_json,
    compute_receipt_sha256,
    issue_decision_receipt,
    verify_receipt,
)
from claimgate.domain import WorkflowState
from claimgate.integrations.foxit_esign import ESignSendResult, Signer
from claimgate.policy_profiles import FINANCIAL_HIGH_RISK
from claimgate.semantic import SemanticEngine

FIXED_TIME = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


class AuditPdfAdapter:
    def __init__(self, token: str = "audit-source") -> None:
        self.token = token
        self.rendered_html: str | None = None

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        self.rendered_html = html
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\n" + self.token.encode("ascii"))
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        text = """ClaimGate Controlled Agreement
Party name: Acme Corporation
Contract amount: USD 12,500.00
Quantity: 250
Delivery date: 2026-09-30
Scope: Istanbul pilot deployment
Deliverable: 250 configured devices
"""
        output_path.write_text(text, encoding="utf-8")
        return text


class LocalSender:
    def send_pdf_for_signature(
        self, pdf_path: Path, signer: Signer
    ) -> ESignSendResult:
        return ESignSendResult(folder_id="local-folder-1")


async def verified_result(tmp_path: Path, draft, *, token: str = "audit-source"):
    bundle = build_phase3_preset(draft, Phase3Preset.PASS)
    return await Phase3Workflow(
        AuditPdfAdapter(token), SemanticEngine(bundle.scripted_provider)
    ).run(
        run_id="audit-run",
        draft=draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / f"{token}.pdf",
    )


def verification_context(result, *, approval=None, previous=None):
    return ReceiptVerificationContext(
        pdf_path=result.pdf_path,
        evidence=result.evidence,
        policy_profile=result.selected_policy_profile,
        approval=approval,
        expected_previous_receipt_sha256=previous,
    )


def rehash(receipt: DecisionReceipt, **updates) -> DecisionReceipt:
    unsigned = receipt.model_copy(
        update={**updates, "receipt_sha256": "0" * 64}
    )
    return unsigned.model_copy(
        update={"receipt_sha256": compute_receipt_sha256(unsigned)}
    )


@pytest.mark.asyncio
async def test_identical_logical_receipts_have_identical_canonical_hashes(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)

    first = issue_decision_receipt(result=result, created_at=FIXED_TIME)
    second = issue_decision_receipt(result=result, created_at=FIXED_TIME)

    assert first == second
    assert first.receipt_sha256 == second.receipt_sha256
    assert canonical_receipt_json(first) == canonical_receipt_json(second)


@pytest.mark.asyncio
async def test_protected_artifact_and_policy_fields_change_receipt_hash(
    tmp_path: Path, phase2_draft
) -> None:
    receipt = issue_decision_receipt(
        result=await verified_result(tmp_path, phase2_draft),
        created_at=FIXED_TIME,
    )
    changed_pdf = rehash(receipt, pdf_sha256="1" * 64)
    changed_evidence = rehash(
        receipt,
        evidence=receipt.evidence.model_copy(
            update={"evidence_sha256": "2" * 64}
        ),
    )
    changed_policy = rehash(
        receipt,
        policy=receipt.policy.model_copy(
            update={
                "policy_profile_id": FINANCIAL_HIGH_RISK.id,
                "policy_profile_sha256": FINANCIAL_HIGH_RISK.profile_hash,
            }
        ),
    )

    assert len(
        {
            receipt.receipt_sha256,
            changed_pdf.receipt_sha256,
            changed_evidence.receipt_sha256,
            changed_policy.receipt_sha256,
        }
    ) == 4


@pytest.mark.asyncio
async def test_claim_order_is_semantically_canonical(
    tmp_path: Path, phase2_draft
) -> None:
    receipt = issue_decision_receipt(
        result=await verified_result(tmp_path, phase2_draft),
        created_at=FIXED_TIME,
    )
    reversed_payload = receipt.model_dump(mode="python")
    reversed_payload["claims"] = list(reversed(receipt.claims))
    reordered = DecisionReceipt.model_validate(reversed_payload)

    assert reordered.claims == receipt.claims
    assert compute_receipt_sha256(reordered) == receipt.receipt_sha256


@pytest.mark.asyncio
async def test_approval_and_esign_metadata_are_integrity_bound(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)
    outcome = ApprovalSendService(LocalSender()).approve_and_send(
        result=result,
        signer=Signer("audit@example.invalid", "Audit", "Signer"),
        approved_by="Audit reviewer",
        confirmed=True,
    )
    sent = issue_decision_receipt(
        result=result,
        created_at=FIXED_TIME,
        approval=outcome.approval,
        esign_status=ReceiptESignStatus.SENT,
        foxit_identifier=outcome.folder_id,
    )
    changed_approval = sent.model_copy(
        update={
            "approval": sent.approval.model_copy(
                update={"approved_at": datetime(2026, 8, 19, 13, 0, tzinfo=timezone.utc)}
            )
        }
    )
    changed_esign = sent.model_copy(
        update={
            "esign": ReceiptESignSummary(
                status=ReceiptESignStatus.SENT,
                foxit_identifier="different-folder",
            )
        }
    )

    assert compute_receipt_sha256(changed_approval) != sent.receipt_sha256
    assert compute_receipt_sha256(changed_esign) != sent.receipt_sha256
    assert verify_receipt(
        sent, verification_context(result, approval=outcome.approval)
    ).status is ReceiptVerificationStatus.VERIFIED


@pytest.mark.asyncio
async def test_receipt_tampering_and_broken_chain_are_detected(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)
    receipt = issue_decision_receipt(
        result=result,
        previous_receipt_sha256="a" * 64,
        created_at=FIXED_TIME,
    )
    tampered = receipt.model_copy(update={"pdf_filename": "changed.pdf"})
    tamper_check = verify_receipt(
        tampered, verification_context(result, previous="a" * 64)
    )
    chain_check = verify_receipt(
        receipt, verification_context(result, previous="b" * 64)
    )

    assert tamper_check.status is ReceiptVerificationStatus.TAMPERED
    assert "RECEIPT_INTEGRITY_FAILURE" in tamper_check.blocker_codes
    assert chain_check.status is ReceiptVerificationStatus.TAMPERED
    assert chain_check.blocker_codes == ("RECEIPT_CHAIN_LINK_MISMATCH",)


@pytest.mark.asyncio
async def test_human_pdf_cannot_override_canonical_json_or_policy_decision(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)
    decision_before = result.decision
    receipt = issue_decision_receipt(result=result, created_at=FIXED_TIME)
    adapter = AuditPdfAdapter("HUMAN-PDF-SAYS-BLOCKED")
    generated = await DecisionReceiptPdfGenerator(lambda: adapter).generate(
        receipt, tmp_path / "human-readable-receipt.pdf"
    )

    assert b"HUMAN-PDF-SAYS-BLOCKED" in generated.read_bytes()
    assert receipt.final_decision is ReceiptDecision.PASS
    assert result.decision == decision_before
    assert "canonical JSON receipt" in adapter.rendered_html
    assert receipt.receipt_sha256 in adapter.rendered_html
    verification = verify_receipt(receipt, verification_context(result))
    assert verification.status is ReceiptVerificationStatus.VERIFIED
    assert result.workflow.state is WorkflowState.READY_FOR_APPROVAL


@pytest.mark.asyncio
async def test_receipt_current_artifact_verification_detects_pdf_and_evidence_changes(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)
    receipt = issue_decision_receipt(result=result, created_at=FIXED_TIME)
    changed_evidence = (
        result.evidence[0].__class__(
            source_id=result.evidence[0].source_id,
            title=result.evidence[0].title,
            content=result.evidence[0].content + "\nchanged",
        ),
        *result.evidence[1:],
    )
    context = ReceiptVerificationContext(
        pdf_path=result.pdf_path,
        evidence=changed_evidence,
        policy_profile=result.selected_policy_profile,
        approval=None,
        expected_previous_receipt_sha256=None,
    )

    evidence_verification = verify_receipt(receipt, context)

    result.pdf_path.write_bytes(result.pdf_path.read_bytes() + b"\ntampered")
    pdf_verification = verify_receipt(
        receipt, verification_context(result)
    )

    assert evidence_verification.status is ReceiptVerificationStatus.TAMPERED
    assert "RECEIPT_EVIDENCE_HASH_MISMATCH" in evidence_verification.blocker_codes
    assert pdf_verification.status is ReceiptVerificationStatus.TAMPERED
    assert "RECEIPT_PDF_HASH_MISMATCH" in pdf_verification.blocker_codes


@pytest.mark.asyncio
async def test_receipt_binds_action_sha256_and_version_is_v3(
    tmp_path: Path, phase2_draft
) -> None:
    result = await verified_result(tmp_path, phase2_draft)
    receipt = issue_decision_receipt(result=result, created_at=FIXED_TIME)
    expected_action_sha256 = compute_action_sha256(build_sign_document_action(result))

    assert receipt.receipt_version == RECEIPT_VERSION
    assert RECEIPT_VERSION.endswith("-v3")
    assert receipt.action_type.value == "SIGN_DOCUMENT"
    assert receipt.action_sha256 == expected_action_sha256
    assert receipt.action_risk.value == "IRREVERSIBLE"
    assert receipt.execution_capability.adapter == "FOXIT_ESIGN"
    assert receipt.execution_capability.live_execution is True

    changed_action_hash = rehash(receipt, action_sha256="1" * 64)
    assert changed_action_hash.receipt_sha256 != receipt.receipt_sha256
