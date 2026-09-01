"""Phase 3 orchestration: Foxit artifact, semantic inputs, deterministic policy."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from claimgate.application.models import DraftDocument
from claimgate.application.renderer import AgreementRenderer
from claimgate.application.workflow import PdfDocumentAdapter
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
from claimgate.evidence_graph import EvidenceGraph
from claimgate.evidence_graph.builder import build_evidence_graph
from claimgate.policy_profiles import (
    STANDARD_CONTRACT,
    PolicyEvaluationContext,
    PolicyProfile,
    PolicyProfileEvaluator,
    ProfilePolicyDecision,
)
from claimgate.semantic import (
    EvidenceComparison,
    EvidenceDocument,
    ExtractedClaim,
    SemanticEngine,
)
from claimgate.semantic.engine import SemanticOutputError


class Phase3Progress(str, Enum):
    GENERATING_DOCUMENT = "generating_document"
    READING_DOCUMENT = "reading_document"
    EXTRACTING_PDF = "extracting_pdf"
    EXTRACTING_CLAIMS = "extracting_claims"
    CHECKING_EVIDENCE = "checking_evidence"
    APPLYING_POLICY = "applying_policy"


class ProgressObserver(Protocol):
    def __call__(self, progress: Phase3Progress) -> None: ...


@dataclass(frozen=True)
class Phase3Result:
    workflow: WorkflowRun
    pdf_path: Path
    extracted_text_path: Path
    extracted_text: str
    extracted_claims: tuple[ExtractedClaim, ...]
    claims: tuple[Claim, ...]
    evidence_documents: tuple[EvidenceDocument, ...]
    evidence: tuple[EvidenceSource, ...]
    verification: VerificationSnapshot
    semantic_comparisons: tuple[EvidenceComparison, ...]
    evidence_graph: EvidenceGraph | None
    selected_policy_profile: PolicyProfile
    baseline_decision: PolicyDecision
    profile_decision: ProfilePolicyDecision
    decision: PolicyDecision
    semantic_failure: str | None


class Phase3Workflow:
    """The semantic engine supplies facts; only Phase 1 policy supplies a decision."""

    def __init__(
        self,
        pdf_adapter: PdfDocumentAdapter,
        semantic_engine: SemanticEngine,
        *,
        renderer: AgreementRenderer | None = None,
        policy: DeterministicPolicyEngine | None = None,
        profile_evaluator: PolicyProfileEvaluator | None = None,
    ) -> None:
        self._pdf_adapter = pdf_adapter
        self._semantic_engine = semantic_engine
        self._renderer = renderer or AgreementRenderer()
        self._policy = policy or DeterministicPolicyEngine()
        self._profile_evaluator = profile_evaluator or PolicyProfileEvaluator()

    async def run(
        self,
        *,
        run_id: str,
        draft: DraftDocument,
        evidence_documents: Sequence[EvidenceDocument],
        output_path: Path,
        policy_profile: PolicyProfile | None = None,
        progress_observer: ProgressObserver | None = None,
    ) -> Phase3Result:
        workflow = WorkflowRun(run_id)
        workflow.start_generation()

        self._report(progress_observer, Phase3Progress.GENERATING_DOCUMENT)
        rendered_html = self._renderer.render(draft)
        generated_path = await self._pdf_adapter.generate_pdf_from_html(
            rendered_html, output_path
        )
        generated_path = generated_path.resolve()
        return await self._finish(
            workflow=workflow,
            generated_path=generated_path,
            evidence_documents=evidence_documents,
            policy_profile=policy_profile,
            progress_observer=progress_observer,
        )

    async def run_from_document(
        self,
        *,
        run_id: str,
        pdf_path: Path,
        evidence_documents: Sequence[EvidenceDocument],
        output_path: Path,
        policy_profile: PolicyProfile | None = None,
        progress_observer: ProgressObserver | None = None,
    ) -> Phase3Result:
        """Same pipeline as ``run``, but for a document the user already
        uploaded: skip HTML rendering / Foxit generation and verify the
        uploaded PDF's own bytes."""

        workflow = WorkflowRun(run_id)
        workflow.start_generation()

        self._report(progress_observer, Phase3Progress.READING_DOCUMENT)
        if pdf_path.resolve() != output_path.resolve():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_bytes(pdf_path.read_bytes())
        generated_path = output_path.resolve()
        return await self._finish(
            workflow=workflow,
            generated_path=generated_path,
            evidence_documents=evidence_documents,
            policy_profile=policy_profile,
            progress_observer=progress_observer,
        )

    async def _finish(
        self,
        *,
        workflow: WorkflowRun,
        generated_path: Path,
        evidence_documents: Sequence[EvidenceDocument],
        policy_profile: PolicyProfile | None,
        progress_observer: ProgressObserver | None,
    ) -> Phase3Result:
        verified_pdf_hash = pdf_sha256(generated_path.read_bytes())

        evidence_documents_tuple = tuple(evidence_documents)
        evidence = tuple(document.source for document in evidence_documents_tuple)
        verified_evidence_hash = evidence_sha256(evidence)

        extracted_text_path = generated_path.with_suffix(".txt")
        self._report(progress_observer, Phase3Progress.EXTRACTING_PDF)
        extracted_text = await self._pdf_adapter.extract_text_from_pdf(
            generated_path, extracted_text_path
        )

        extracted_claims: tuple[ExtractedClaim, ...] = ()
        claims: tuple[Claim, ...] = ()
        semantic_comparisons: tuple[EvidenceComparison, ...] = ()
        evidence_graph: EvidenceGraph | None = None
        semantic_failure: str | None = None
        try:
            self._report(progress_observer, Phase3Progress.EXTRACTING_CLAIMS)
            extracted_claims = await self._semantic_engine.extract_claims(extracted_text)
            claims = self._semantic_engine.to_domain_claims(extracted_claims)
            self._report(progress_observer, Phase3Progress.CHECKING_EVIDENCE)
            verification_bundle = await self._semantic_engine.verify_evidence_bundle(
                claims=extracted_claims,
                evidence=evidence,
                verified_pdf_sha256=verified_pdf_hash,
                verified_evidence_sha256=verified_evidence_hash,
            )
            verification = verification_bundle.snapshot
            semantic_comparisons = verification_bundle.comparisons
            evidence_graph = build_evidence_graph(
                claims=extracted_claims,
                evidence_documents=evidence_documents_tuple,
                comparisons=semantic_comparisons,
            )
        except (SemanticOutputError, ValueError) as exc:
            semantic_failure = str(exc)
            semantic_comparisons = ()
            evidence_graph = None
            verification = self._semantic_engine.failed_snapshot(
                pdf_sha256=verified_pdf_hash,
                evidence=evidence,
                reason=semantic_failure,
            )

        current_pdf_hash = pdf_sha256(generated_path.read_bytes())
        current_evidence_hash = evidence_sha256(evidence)
        self._report(progress_observer, Phase3Progress.APPLYING_POLICY)
        workflow.start_verification(
            pdf_sha256=current_pdf_hash,
            evidence_sha256=current_evidence_hash,
        )
        baseline_decision = self._policy.evaluate(
            claims=claims,
            evidence=evidence,
            verification=verification,
            current_pdf_sha256=current_pdf_hash,
        )
        selected_policy_profile = policy_profile or STANDARD_CONTRACT
        effective_evaluation = self._profile_evaluator.evaluate(
            PolicyEvaluationContext(
                baseline_decision=baseline_decision,
                selected_profile=selected_policy_profile,
                evidence_graph=evidence_graph,
            )
        )
        decision = effective_evaluation.final_decision
        workflow.apply_policy(decision)
        return Phase3Result(
            workflow=workflow,
            pdf_path=generated_path,
            extracted_text_path=extracted_text_path,
            extracted_text=extracted_text,
            extracted_claims=extracted_claims,
            claims=claims,
            evidence_documents=evidence_documents_tuple,
            evidence=evidence,
            verification=verification,
            semantic_comparisons=semantic_comparisons,
            evidence_graph=evidence_graph,
            selected_policy_profile=selected_policy_profile,
            baseline_decision=baseline_decision,
            profile_decision=effective_evaluation.profile_decision,
            decision=decision,
            semantic_failure=semantic_failure,
        )

    @staticmethod
    def _report(
        observer: ProgressObserver | None, progress: Phase3Progress
    ) -> None:
        if observer is not None:
            observer(progress)
