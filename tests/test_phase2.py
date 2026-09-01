from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import load_dotenv

from claimgate.application import (
    AgreementRenderer,
    FixtureVerifier,
    Phase2Workflow,
    build_fixture_bundle,
)
from claimgate.config import FoxitPdfSettings
from claimgate.domain import PolicyOutcome, WorkflowState, pdf_sha256
from claimgate.integrations.foxit_pdf import FoxitPdfClient


class FakeFoxitPdfAdapter:
    def __init__(self, extracted_text: str) -> None:
        self.extracted_text = extracted_text
        self.calls: list[str] = []
        self.rendered_html: str | None = None

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        self.calls.append("generate")
        self.rendered_html = html
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\nexact-generated-artifact")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        self.calls.append("extract")
        output_path.write_text(self.extracted_text)
        return self.extracted_text


class TamperingFixtureVerifier(FixtureVerifier):
    def __init__(self, pdf_path: Path) -> None:
        self._pdf_path = pdf_path

    def verify(self, **arguments):
        snapshot = super().verify(**arguments)
        with self._pdf_path.open("ab") as pdf_file:
            pdf_file.write(b"\ntampered-after-fixture-verification")
        return snapshot


def extracted_fixture_text(draft) -> str:
    fixtures, _ = build_fixture_bundle(draft)
    return "\n".join(fixture.document_phrase for fixture in fixtures)


def test_controlled_template_renders_fixed_fields_and_escapes_html(phase2_draft) -> None:
    dangerous_draft = replace(phase2_draft, party_name="<script>alert(1)</script>")

    html = AgreementRenderer().render(dangerous_draft)

    assert "Party name:" in html
    assert "Contract amount:" in html
    assert "USD 12,500.00" in html
    assert "Quantity:" in html
    assert "Delivery date:" in html
    assert "Scope:" in html
    assert "Deliverable:" in html
    assert "${s:1:______}" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


@pytest.mark.asyncio
async def test_workflow_verifies_and_binds_exact_generated_artifact(
    tmp_path: Path, phase2_draft
) -> None:
    adapter = FakeFoxitPdfAdapter(extracted_fixture_text(phase2_draft))

    result = await Phase2Workflow(adapter).run(
        run_id="phase2-pass",
        draft=phase2_draft,
        output_path=tmp_path / "agreement.pdf",
    )

    artifact_hash = pdf_sha256(result.pdf_path.read_bytes())
    assert adapter.calls == ["generate", "extract"]
    assert result.verification.pdf_sha256 == artifact_hash
    assert result.decision.pdf_sha256 == artifact_hash
    assert result.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert result.extracted_text_path.read_text() == extracted_fixture_text(phase2_draft)


@pytest.mark.asyncio
async def test_pdf_changed_after_verification_hash_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    output_path = tmp_path / "agreement.pdf"
    adapter = FakeFoxitPdfAdapter(extracted_fixture_text(phase2_draft))

    result = await Phase2Workflow(
        adapter,
        verifier=TamperingFixtureVerifier(output_path),
    ).run(
        run_id="phase2-tamper",
        draft=phase2_draft,
        output_path=output_path,
    )

    assert result.verification.pdf_sha256 != pdf_sha256(result.pdf_path.read_bytes())
    assert result.decision.outcome is PolicyOutcome.BLOCKED
    assert result.workflow.state is WorkflowState.BLOCKED
    assert "PDF_HASH_CHANGED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.asyncio
async def test_missing_claim_in_extracted_pdf_text_blocks(
    tmp_path: Path, phase2_draft
) -> None:
    extracted_text = extracted_fixture_text(phase2_draft).replace(
        "Deliverable: 250 configured devices",
        "",
    )
    adapter = FakeFoxitPdfAdapter(extracted_text)

    result = await Phase2Workflow(adapter).run(
        run_id="phase2-missing-text",
        draft=phase2_draft,
        output_path=tmp_path / "agreement.pdf",
    )

    assert result.decision.outcome is PolicyOutcome.BLOCKED
    assert result.workflow.state is WorkflowState.BLOCKED
    assert "VERIFICATION_FAILED" in {blocker.code for blocker in result.decision.blockers}


@pytest.mark.live
@pytest.mark.asyncio
async def test_optional_live_foxit_phase2(tmp_path: Path, phase2_draft) -> None:
    if os.getenv("CLAIMGATE_RUN_LIVE_FOXIT") != "1":
        pytest.skip("Set CLAIMGATE_RUN_LIVE_FOXIT=1 to make live Foxit PDF calls")
    load_dotenv()
    result = await Phase2Workflow(FoxitPdfClient(FoxitPdfSettings.from_env())).run(
        run_id="phase2-pytest-live",
        draft=phase2_draft,
        output_path=tmp_path / "live-agreement.pdf",
    )

    assert result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert result.verification.pdf_sha256 == pdf_sha256(result.pdf_path.read_bytes())
    assert all(
        verification.status.value == "SUPPORTED"
        for verification in result.verification.results
    )
