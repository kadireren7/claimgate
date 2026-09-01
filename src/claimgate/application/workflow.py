"""Phase 2 orchestration from controlled draft to deterministic policy decision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from claimgate.application.fixture_verification import (
    FixtureVerifier,
    build_fixture_bundle,
)
from claimgate.application.models import DraftDocument
from claimgate.application.renderer import AgreementRenderer
from claimgate.domain import (
    Claim,
    DeterministicPolicyEngine,
    EvidenceSource,
    PolicyDecision,
    VerificationSnapshot,
    WorkflowRun,
    evidence_sha256,
    pdf_sha256,
)


class PdfDocumentAdapter(Protocol):
    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path: ...

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str: ...


@dataclass(frozen=True)
class Phase2Result:
    workflow: WorkflowRun
    pdf_path: Path
    extracted_text_path: Path
    extracted_text: str
    claims: tuple[Claim, ...]
    evidence: tuple[EvidenceSource, ...]
    verification: VerificationSnapshot
    decision: PolicyDecision


class Phase2Workflow:
    def __init__(
        self,
        pdf_adapter: PdfDocumentAdapter,
        *,
        renderer: AgreementRenderer | None = None,
        verifier: FixtureVerifier | None = None,
        policy: DeterministicPolicyEngine | None = None,
    ) -> None:
        self._pdf_adapter = pdf_adapter
        self._renderer = renderer or AgreementRenderer()
        self._verifier = verifier or FixtureVerifier()
        self._policy = policy or DeterministicPolicyEngine()

    async def run(
        self,
        *,
        run_id: str,
        draft: DraftDocument,
        output_path: Path,
    ) -> Phase2Result:
        workflow = WorkflowRun(run_id)
        workflow.start_generation()

        rendered_html = self._renderer.render(draft)
        generated_path = await self._pdf_adapter.generate_pdf_from_html(
            rendered_html, output_path
        )
        generated_path = generated_path.resolve()
        verified_pdf_hash = pdf_sha256(generated_path.read_bytes())

        fixtures, evidence = build_fixture_bundle(draft)
        evidence_hash = evidence_sha256(evidence)

        extracted_text_path = generated_path.with_suffix(".txt")
        extracted_text = await self._pdf_adapter.extract_text_from_pdf(
            generated_path, extracted_text_path
        )
        verification = self._verifier.verify(
            fixtures=fixtures,
            evidence=evidence,
            extracted_text=extracted_text,
            verified_pdf_sha256=verified_pdf_hash,
        )

        current_pdf_hash = pdf_sha256(generated_path.read_bytes())
        workflow.start_verification(
            pdf_sha256=current_pdf_hash,
            evidence_sha256=evidence_hash,
        )
        claims = tuple(fixture.claim for fixture in fixtures)
        decision = self._policy.evaluate(
            claims=claims,
            evidence=evidence,
            verification=verification,
            current_pdf_sha256=current_pdf_hash,
        )
        workflow.apply_policy(decision)
        return Phase2Result(
            workflow=workflow,
            pdf_path=generated_path,
            extracted_text_path=extracted_text_path,
            extracted_text=extracted_text,
            claims=claims,
            evidence=evidence,
            verification=verification,
            decision=decision,
        )
