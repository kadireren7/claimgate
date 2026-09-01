from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import load_dotenv

from claimgate.application import (
    Phase3Preset,
    Phase3Workflow,
    build_phase3_preset,
)
from claimgate.config import FoxitPdfSettings
from claimgate.domain import (
    DeterministicPolicyEngine,
    PolicyOutcome,
    WorkflowState,
    pdf_sha256,
)
from claimgate.evidence_graph import EvidenceAuthority, EvidenceRelationship
from claimgate.evidence_graph.builder import build_evidence_graph
from claimgate.integrations.foxit_pdf import FoxitPdfClient
from claimgate.policy_profiles import (
    FINANCIAL_HIGH_RISK,
    STANDARD_CONTRACT,
    ProfilePolicyOutcome,
)
from claimgate.semantic import ScriptedSemanticProvider, SemanticEngine, SemanticOperation


class FakeFoxitPdfAdapter:
    def __init__(self, extracted_text: str) -> None:
        self.extracted_text = extracted_text
        self.calls: list[str] = []

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        self.calls.append("generate")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\nphase3-exact-generated-artifact")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        self.calls.append("extract")
        output_path.write_text(self.extracted_text)
        return self.extracted_text


class TamperingProvider:
    def __init__(self, delegate, pdf_path: Path) -> None:
        self._delegate = delegate
        self._pdf_path = pdf_path

    async def complete_structured(self, request):
        response = await self._delegate.complete_structured(request)
        if request.operation is SemanticOperation.VERIFY_EVIDENCE:
            with self._pdf_path.open("ab") as pdf_file:
                pdf_file.write(b"\ntampered-after-semantic-verification")
        return response


def extracted_agreement_text(draft) -> str:
    return "\n".join(
        (
            f"Party name: {draft.party_name}",
            f"Contract amount: {draft.amount_display}",
            f"Quantity: {draft.quantity}",
            f"Delivery date: {draft.delivery_date_display}",
            f"Scope: {draft.scope}",
            f"Deliverable: {draft.deliverable}",
        )
    )


async def run_preset(
    tmp_path: Path, draft, preset: Phase3Preset, policy_profile=None
):
    bundle = build_phase3_preset(draft, preset)
    adapter = FakeFoxitPdfAdapter(extracted_agreement_text(draft))
    result = await Phase3Workflow(
        adapter,
        SemanticEngine(bundle.scripted_provider),
    ).run(
        run_id=f"phase3-{preset.value}",
        draft=draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / f"{preset.value}.pdf",
        policy_profile=policy_profile,
    )
    return adapter, result


@pytest.mark.asyncio
async def test_pass_preset_reaches_ready_for_approval(tmp_path: Path, phase2_draft) -> None:
    adapter, result = await run_preset(tmp_path, phase2_draft, Phase3Preset.PASS)

    artifact_hash = pdf_sha256(result.pdf_path.read_bytes())
    assert adapter.calls == ["generate", "extract"]
    assert result.verification.pdf_sha256 == artifact_hash
    assert result.decision.pdf_sha256 == artifact_hash
    assert result.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert result.semantic_failure is None
    assert len(result.extracted_claims) == 6
    assert all(claim.critical for claim in result.extracted_claims)


@pytest.mark.asyncio
async def test_same_document_passes_standard_but_blocks_financial_high_risk(
    tmp_path: Path, phase2_draft
) -> None:
    _, standard = await run_preset(
        tmp_path, phase2_draft, Phase3Preset.PASS, STANDARD_CONTRACT
    )
    _, financial = await run_preset(
        tmp_path, phase2_draft, Phase3Preset.PASS, FINANCIAL_HIGH_RISK
    )

    assert standard.pdf_path.read_bytes() == financial.pdf_path.read_bytes()
    assert standard.baseline_decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert financial.baseline_decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert standard.profile_decision.outcome is ProfilePolicyOutcome.PASS
    assert standard.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert financial.profile_decision.outcome is ProfilePolicyOutcome.BLOCK
    assert financial.workflow.state is WorkflowState.BLOCKED
    assert financial.decision.outcome is PolicyOutcome.BLOCKED
    assert financial.profile_decision.blockers[0].code == (
        "PROFILE_INSUFFICIENT_SUPPORTING_SOURCES"
    )


@pytest.mark.asyncio
async def test_block_preset_has_critical_money_conflict(tmp_path: Path, phase2_draft) -> None:
    _, result = await run_preset(tmp_path, phase2_draft, Phase3Preset.BLOCK)

    money_result = next(
        item for item in result.verification.results if item.claim_id == "money"
    )
    assert money_result.status.value == "CONFLICTING"
    assert money_result.quotation == "Contract amount: USD 15,000.00"
    assert result.workflow.state is WorkflowState.BLOCKED
    assert result.decision.outcome is PolicyOutcome.BLOCKED
    assert "CRITICAL_CLAIM_CONFLICTING" in {
        blocker.code for blocker in result.decision.blockers
    }


@pytest.mark.asyncio
async def test_evidence_graph_preset_keeps_support_and_conflict_visible(
    tmp_path: Path, phase2_draft
) -> None:
    _, result = await run_preset(
        tmp_path, phase2_draft, Phase3Preset.EVIDENCE_GRAPH
    )

    assert result.evidence_graph is not None
    money_edges = [
        edge for edge in result.evidence_graph.edges if edge.claim_id == "money"
    ]
    assert [edge.relationship for edge in money_edges] == [
        EvidenceRelationship.SUPPORTS,
        EvidenceRelationship.SUPPORTS,
        EvidenceRelationship.CONFLICTS,
    ]
    assert result.evidence_graph.summary.support_count == 7
    assert result.evidence_graph.summary.conflict_count == 1
    conflicting_source = next(
        source
        for source in result.evidence_graph.evidence
        if source.source_id == money_edges[-1].evidence_id
    )
    assert conflicting_source.authority is EvidenceAuthority.UNVERIFIED_EXTERNAL
    assert result.workflow.state is WorkflowState.BLOCKED
    assert result.decision.outcome is PolicyOutcome.BLOCKED
    money_result = next(
        item for item in result.verification.results if item.claim_id == "money"
    )
    assert money_result.status.value == "CONFLICTING"


@pytest.mark.asyncio
async def test_graph_construction_does_not_alter_policy_decision(
    tmp_path: Path, phase2_draft
) -> None:
    _, result = await run_preset(
        tmp_path, phase2_draft, Phase3Preset.EVIDENCE_GRAPH
    )
    policy = DeterministicPolicyEngine()
    policy_arguments = {
        "claims": result.claims,
        "evidence": result.evidence,
        "verification": result.verification,
        "current_pdf_sha256": pdf_sha256(result.pdf_path.read_bytes()),
    }
    decision_before = policy.evaluate(**policy_arguments)

    graph = build_evidence_graph(
        claims=result.extracted_claims,
        evidence_documents=result.evidence_documents,
        comparisons=result.semantic_comparisons,
    )
    decision_after = policy.evaluate(**policy_arguments)

    assert graph == result.evidence_graph
    assert decision_before == decision_after == result.decision


@pytest.mark.asyncio
async def test_source_authority_labels_cannot_bypass_deterministic_policy(
    tmp_path: Path, phase2_draft
) -> None:
    _, result = await run_preset(
        tmp_path, phase2_draft, Phase3Preset.EVIDENCE_GRAPH
    )
    relabeled_documents = tuple(
        replace(document, authority=EvidenceAuthority.AUTHORITATIVE_INTERNAL)
        for document in result.evidence_documents
    )

    relabeled_graph = build_evidence_graph(
        claims=result.extracted_claims,
        evidence_documents=relabeled_documents,
        comparisons=result.semantic_comparisons,
    )
    decision = DeterministicPolicyEngine().evaluate(
        claims=result.claims,
        evidence=result.evidence,
        verification=result.verification,
        current_pdf_sha256=pdf_sha256(result.pdf_path.read_bytes()),
    )

    assert relabeled_graph.summary.authoritative_conflict_count == 1
    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "CRITICAL_CLAIM_CONFLICTING" in {
        blocker.code for blocker in decision.blockers
    }


@pytest.mark.asyncio
async def test_invented_quote_becomes_failed_snapshot_and_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    bundle = build_phase3_preset(phase2_draft, Phase3Preset.PASS)
    original_provider = bundle.scripted_provider

    class InventingProvider:
        async def complete_structured(self, request):
            response = await original_provider.complete_structured(request)
            if request.operation is SemanticOperation.VERIFY_EVIDENCE:
                response["results"][0]["quotation"] = "This quotation does not exist"
            return response

    result = await Phase3Workflow(
        FakeFoxitPdfAdapter(extracted_agreement_text(phase2_draft)),
        SemanticEngine(InventingProvider()),
    ).run(
        run_id="phase3-invented-quote",
        draft=phase2_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "invented.pdf",
    )

    assert result.verification.succeeded is False
    assert result.semantic_failure == "Invented evidence quotation for claim: party"
    assert result.workflow.state is WorkflowState.BLOCKED
    assert "VERIFICATION_FAILED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.asyncio
async def test_malformed_model_output_becomes_failed_snapshot_and_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    bundle = build_phase3_preset(phase2_draft, Phase3Preset.PASS)
    result = await Phase3Workflow(
        FakeFoxitPdfAdapter(extracted_agreement_text(phase2_draft)),
        SemanticEngine(ScriptedSemanticProvider([{"unexpected": "shape"}])),
    ).run(
        run_id="phase3-malformed",
        draft=phase2_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "malformed.pdf",
    )

    assert result.extracted_claims == ()
    assert result.verification.succeeded is False
    assert result.workflow.state is WorkflowState.BLOCKED
    assert result.decision.outcome is PolicyOutcome.BLOCKED


@pytest.mark.asyncio
async def test_incomplete_verification_becomes_failed_snapshot_and_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    bundle = build_phase3_preset(phase2_draft, Phase3Preset.PASS)

    class IncompleteVerificationProvider:
        async def complete_structured(self, request):
            if request.operation is SemanticOperation.VERIFY_EVIDENCE:
                return {"complete": False, "results": []}
            return await bundle.scripted_provider.complete_structured(request)

    result = await Phase3Workflow(
        FakeFoxitPdfAdapter(extracted_agreement_text(phase2_draft)),
        SemanticEngine(IncompleteVerificationProvider()),
    ).run(
        run_id="phase3-incomplete-verification",
        draft=phase2_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "incomplete.pdf",
    )

    assert result.verification.succeeded is False
    assert result.semantic_failure == "Evidence comparison was marked incomplete"
    assert result.workflow.state is WorkflowState.BLOCKED
    assert "VERIFICATION_FAILED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.asyncio
async def test_pdf_changed_after_semantic_verification_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    output_path = tmp_path / "tampered.pdf"
    bundle = build_phase3_preset(phase2_draft, Phase3Preset.PASS)
    result = await Phase3Workflow(
        FakeFoxitPdfAdapter(extracted_agreement_text(phase2_draft)),
        SemanticEngine(TamperingProvider(bundle.scripted_provider, output_path)),
    ).run(
        run_id="phase3-pdf-tamper",
        draft=phase2_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=output_path,
    )

    assert result.verification.pdf_sha256 != pdf_sha256(result.pdf_path.read_bytes())
    assert result.workflow.state is WorkflowState.BLOCKED
    assert "PDF_HASH_CHANGED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.asyncio
async def test_changed_evidence_still_blocks_under_phase1_policy(
    tmp_path: Path, phase2_draft
) -> None:
    _, result = await run_preset(tmp_path, phase2_draft, Phase3Preset.PASS)
    changed = (
        replace(
            result.evidence[0],
            content=result.evidence[0].content + "\nChanged after verification",
        ),
        *result.evidence[1:],
    )

    decision = DeterministicPolicyEngine().evaluate(
        claims=result.claims,
        evidence=changed,
        verification=result.verification,
        current_pdf_sha256=pdf_sha256(result.pdf_path.read_bytes()),
    )

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert "EVIDENCE_HASH_CHANGED" in {blocker.code for blocker in decision.blockers}


@pytest.mark.live
@pytest.mark.asyncio
async def test_optional_live_foxit_phase3(tmp_path: Path, phase2_draft) -> None:
    if os.getenv("CLAIMGATE_RUN_LIVE_FOXIT") != "1":
        pytest.skip("Set CLAIMGATE_RUN_LIVE_FOXIT=1 to make live Foxit PDF calls")
    load_dotenv()
    bundle = build_phase3_preset(phase2_draft, Phase3Preset.PASS)
    result = await Phase3Workflow(
        FoxitPdfClient(FoxitPdfSettings.from_env()),
        SemanticEngine(bundle.scripted_provider),
    ).run(
        run_id="phase3-pytest-live",
        draft=phase2_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "live-phase3-agreement.pdf",
    )

    assert result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert result.verification.pdf_sha256 == pdf_sha256(result.pdf_path.read_bytes())
    assert result.workflow.state is WorkflowState.READY_FOR_APPROVAL
