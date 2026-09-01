from __future__ import annotations

from pathlib import Path

import pytest

from claimgate.application import (
    Phase3Preset,
    Phase3Workflow,
    build_phase3_preset,
    build_sign_document_action,
)
from claimgate.audit import (
    ReceiptESignStatus,
    ReceiptESignSummary,
    issue_decision_receipt,
)
from claimgate.domain import WorkflowState
from claimgate.replay import (
    ReplayPreset,
    ReplayRequest,
    ReplayStatus,
    ReplayVerifier,
    apply_replay_preset,
    build_audit_timeline,
    capture_artifact_snapshot,
)
from claimgate.semantic import SemanticEngine

EXTRACTED_AGREEMENT = """ClaimGate Controlled Agreement
Party name: Acme Corporation
Contract amount: USD 12,500.00
Quantity: 250
Delivery date: 2026-09-30
Scope: Istanbul pilot deployment
Deliverable: 250 configured devices
"""


class ReplayPdfAdapter:
    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        assert "ClaimGate Controlled Agreement" in html
        output_path.write_bytes(b"%PDF-1.4\nreplay-original")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        output_path.write_text(EXTRACTED_AGREEMENT, encoding="utf-8")
        return EXTRACTED_AGREEMENT


class CountingProvider:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.calls = 0

    async def complete_structured(self, request):
        self.calls += 1
        return await self.delegate.complete_structured(request)


async def replay_fixture(tmp_path: Path, draft):
    bundle = build_phase3_preset(draft, Phase3Preset.PASS)
    provider = CountingProvider(bundle.scripted_provider)
    result = await Phase3Workflow(
        ReplayPdfAdapter(), SemanticEngine(provider)
    ).run(
        run_id="historical-run",
        draft=draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "historical.pdf",
    )
    receipt = issue_decision_receipt(result=result)
    snapshot = capture_artifact_snapshot(
        pdf_path=result.pdf_path,
        evidence=result.evidence,
        policy_profile=result.selected_policy_profile,
        approval=None,
        esign=ReceiptESignSummary(status=ReceiptESignStatus.NOT_ATTEMPTED),
        expected_previous_receipt_sha256=None,
        action=build_sign_document_action(result),
    )
    request = ReplayRequest(
        run_id=result.workflow.run_id,
        receipt_sha256=receipt.receipt_sha256,
    )
    return result, receipt, snapshot, request, provider


@pytest.mark.asyncio
async def test_clean_replay_verifies_every_historical_binding(
    tmp_path: Path, phase2_draft
) -> None:
    result, receipt, snapshot, request, _ = await replay_fixture(
        tmp_path, phase2_draft
    )

    replay = ReplayVerifier().verify(
        request=request,
        receipt=receipt,
        snapshot=snapshot,
    )

    assert replay.status is ReplayStatus.VERIFIED
    assert replay.blocker_codes == ()
    assert all(check.status.value == "PASS" for check in replay.checks)
    assert replay.original_final_decision is receipt.final_decision
    assert replay.original_workflow_state is WorkflowState.READY_FOR_APPROVAL
    assert result.workflow.state is WorkflowState.READY_FOR_APPROVAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("preset", "blocker"),
    [
        (ReplayPreset.PDF_DRIFT, "PDF_HASH_MISMATCH"),
        (ReplayPreset.EVIDENCE_DRIFT, "EVIDENCE_HASH_MISMATCH"),
        (ReplayPreset.POLICY_DRIFT, "POLICY_PROFILE_HASH_MISMATCH"),
    ],
)
async def test_artifact_and_policy_drift_are_distinct_from_receipt_tampering(
    tmp_path: Path, phase2_draft, preset: ReplayPreset, blocker: str
) -> None:
    _, receipt, snapshot, request, _ = await replay_fixture(tmp_path, phase2_draft)

    replay = ReplayVerifier().verify(
        request=request.model_copy(update={"preset": preset}),
        receipt=receipt,
        snapshot=apply_replay_preset(snapshot, preset),
    )

    assert replay.status is ReplayStatus.DRIFT_DETECTED
    assert blocker in replay.blocker_codes
    assert "RECEIPT_INTEGRITY_FAILURE" not in replay.blocker_codes
    assert next(
        check for check in replay.checks if check.check_id == "receipt_integrity"
    ).status.value == "PASS"
    if preset is ReplayPreset.POLICY_DRIFT:
        profile_id = next(
            check for check in replay.checks if check.check_id == "policy_profile_id"
        )
        profile_hash = next(
            check for check in replay.checks if check.check_id == "policy_profile_hash"
        )
        assert profile_id.status.value == "PASS"
        assert profile_hash.status.value == "FAIL"


@pytest.mark.asyncio
async def test_receipt_tampering_reports_invalid_not_artifact_drift(
    tmp_path: Path, phase2_draft
) -> None:
    _, receipt, snapshot, request, _ = await replay_fixture(tmp_path, phase2_draft)
    tampered = receipt.model_copy(update={"pdf_filename": "edited-history.pdf"})

    replay = ReplayVerifier().verify(
        request=request,
        receipt=tampered,
        snapshot=snapshot,
    )

    assert replay.status is ReplayStatus.INVALID_RECEIPT
    assert "RECEIPT_INTEGRITY_FAILURE" in replay.blocker_codes
    assert "PDF_HASH_MISMATCH" not in replay.blocker_codes


@pytest.mark.asyncio
async def test_broken_chain_and_missing_artifact_have_separate_statuses(
    tmp_path: Path, phase2_draft
) -> None:
    _, receipt, snapshot, request, _ = await replay_fixture(tmp_path, phase2_draft)
    broken = ReplayVerifier().verify(
        request=request.model_copy(update={"preset": ReplayPreset.BROKEN_CHAIN}),
        receipt=receipt,
        snapshot=apply_replay_preset(snapshot, ReplayPreset.BROKEN_CHAIN),
    )
    missing_snapshot = snapshot.model_copy(
        update={"pdf_available": False, "pdf_sha256": None}
    )
    missing = ReplayVerifier().verify(
        request=request,
        receipt=receipt,
        snapshot=missing_snapshot,
    )

    assert broken.status is ReplayStatus.CHAIN_BROKEN
    assert broken.blocker_codes == ("PREVIOUS_RECEIPT_CHAIN_MISMATCH",)
    assert missing.status is ReplayStatus.ARTIFACT_MISSING
    assert "PDF_ARTIFACT_MISSING" in missing.blocker_codes
    assert "PDF_HASH_MISMATCH" in missing.blocker_codes


@pytest.mark.asyncio
async def test_replay_has_no_semantic_approval_send_or_state_authority(
    tmp_path: Path, phase2_draft
) -> None:
    result, receipt, snapshot, request, provider = await replay_fixture(
        tmp_path, phase2_draft
    )
    provider_calls = provider.calls
    state_before = result.workflow.state
    decision_before = result.decision

    replay = ReplayVerifier().verify(
        request=request,
        receipt=receipt,
        snapshot=snapshot,
    )

    assert replay.status is ReplayStatus.VERIFIED
    assert provider.calls == provider_calls
    assert result.workflow.state is state_before
    assert result.decision is decision_before
    assert receipt.approval.occurred is False
    assert receipt.esign.status is ReceiptESignStatus.NOT_ATTEMPTED
    assert not hasattr(ReplayVerifier(), "approve")
    assert not hasattr(ReplayVerifier(), "send_pdf_for_signature")


@pytest.mark.asyncio
async def test_timeline_is_derived_without_changing_the_original_decision(
    tmp_path: Path, phase2_draft
) -> None:
    result, receipt, _, _, _ = await replay_fixture(tmp_path, phase2_draft)

    timeline = build_audit_timeline(
        run_id=result.workflow.run_id,
        run_created_at=receipt.created_at,
        receipts=(receipt,),
    )

    assert [event.kind.value for event in timeline] == [
        "RUN_CREATED",
        "VERIFICATION_RECEIPT",
    ]
    assert timeline[-1].receipt_sha256 == receipt.receipt_sha256
    assert timeline[-1].decision is receipt.final_decision
    assert result.decision.outcome.value == "READY_FOR_APPROVAL"


@pytest.mark.asyncio
async def test_replay_detects_action_parameter_drift(
    tmp_path: Path, phase2_draft
) -> None:
    _, receipt, snapshot, request, _ = await replay_fixture(tmp_path, phase2_draft)

    replay = ReplayVerifier().verify(
        request=request.model_copy(update={"preset": ReplayPreset.ACTION_PARAMETER_DRIFT}),
        receipt=receipt,
        snapshot=apply_replay_preset(snapshot, ReplayPreset.ACTION_PARAMETER_DRIFT),
    )

    assert replay.status is ReplayStatus.DRIFT_DETECTED
    assert "ACTION_DRIFT" in replay.blocker_codes
    assert "RECEIPT_INTEGRITY_FAILURE" not in replay.blocker_codes
    action_check = next(
        check for check in replay.checks if check.check_id == "action_binding"
    )
    assert action_check.status.value == "FAIL"
    assert action_check.blocker_code == "ACTION_DRIFT"


def test_replay_module_has_no_semantic_or_signing_dependencies() -> None:
    source = (
        Path(__file__).parents[1]
        / "src"
        / "claimgate"
        / "replay"
        / "verifier.py"
    ).read_text(encoding="utf-8")

    assert "SemanticEngine" not in source
    assert "OpenAI" not in source
    assert "ApprovalSendService" not in source
    assert "FoxitESignClient" not in source
    assert "send_pdf_for_signature" not in source
    assert "WorkflowRun" not in source

