"""Server-side Phase 3 demo presets; browser input never reaches Foxit directly."""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

from claimgate.application.models import DraftDocument
from claimgate.application.phase3_presets import (
    Phase3Preset,
    build_phase3_preset,
)
from claimgate.application.phase3_workflow import (
    PdfDocumentAdapter,
    Phase3Progress,
    Phase3Result,
    Phase3Workflow,
    ProgressObserver,
)
from claimgate.config import FoxitPdfSettings
from claimgate.integrations.foxit_pdf import FoxitPdfClient
from claimgate.policy_profiles import (
    BUILT_IN_PROFILES,
    BuiltInPolicyProfile,
    get_builtin_profile,
)
from claimgate.semantic import EvidenceDocument, OpenAIResponsesProvider, SemanticEngine


class DemoPreset(str, Enum):
    SAFE = "safe"
    CONFLICTING = "conflicting"
    EVIDENCE_GRAPH = "evidence_graph"
    PUBLIC_CERTIFICATION = "public_certification"
    UNVERIFIED_PUBLIC = "unverified_public"


@dataclass(frozen=True)
class DemoPresetDefinition:
    preset: DemoPreset
    title: str
    summary: str
    plain_language_request: str
    phase3_preset: Phase3Preset
    public_fact: str | None = None


PRESET_DEFINITIONS = (
    DemoPresetDefinition(
        preset=DemoPreset.SAFE,
        title="Safe Agreement",
        summary="Every material term matches the authoritative evidence.",
        plain_language_request=(
            "Create a delivery agreement with Acme Corporation for 250 configured devices, "
            "priced at USD 12,500.00, due September 30, 2026, for the Istanbul pilot."
        ),
        phase3_preset=Phase3Preset.PASS,
    ),
    DemoPresetDefinition(
        preset=DemoPreset.CONFLICTING,
        title="Conflicting Agreement",
        summary="The authoritative commercial terms disagree with the document amount.",
        plain_language_request=(
            "Create a delivery agreement with Acme Corporation for 250 configured devices, "
            "priced at USD 12,500.00, due September 30, 2026, for the Istanbul pilot."
        ),
        phase3_preset=Phase3Preset.BLOCK,
    ),
    DemoPresetDefinition(
        preset=DemoPreset.EVIDENCE_GRAPH,
        title="Mixed Evidence Graph",
        summary="Two sources support the amount while one source contradicts it.",
        plain_language_request=(
            "Create a delivery agreement with Acme Corporation for 250 configured devices, "
            "priced at USD 12,500.00, due September 30, 2026, for the Istanbul pilot."
        ),
        phase3_preset=Phase3Preset.EVIDENCE_GRAPH,
    ),
    DemoPresetDefinition(
        preset=DemoPreset.PUBLIC_CERTIFICATION,
        title="Public Certification",
        summary="A certification claim starts unsupported and can use registry evidence.",
        plain_language_request=(
            "Create the agreement and state that Example organization holds Certification X."
        ),
        phase3_preset=Phase3Preset.PUBLIC_CLAIM,
        public_fact="Example organization holds Certification X",
    ),
    DemoPresetDefinition(
        preset=DemoPreset.UNVERIFIED_PUBLIC,
        title="Unverified Public Source",
        summary="A random blog supports the certification claim but remains unverified.",
        plain_language_request=(
            "Create the agreement and state that Example organization holds Certification X."
        ),
        phase3_preset=Phase3Preset.PUBLIC_CLAIM,
        public_fact="Example organization holds Certification X",
    ),
)

PdfAdapterFactory = Callable[[], PdfDocumentAdapter]


class RealDocumentReviewUnavailableError(RuntimeError):
    """Raised when a real (non-scripted) semantic provider isn't configured.

    Reviewing an arbitrary user-uploaded document requires a general-purpose
    semantic provider — the scripted provider only understands the fixed demo
    presets. Fails closed rather than silently falling back to fixture data.
    """


def demo_draft(public_fact: str | None = None) -> DraftDocument:
    return DraftDocument(
        party_name="Acme Corporation",
        contract_amount=Decimal("12500.00"),
        quantity=250,
        delivery_date=date(2026, 9, 30),
        scope="Istanbul pilot deployment",
        deliverable="250 configured devices",
        public_fact=public_fact,
    )


def preset_definition(preset: DemoPreset) -> DemoPresetDefinition:
    return next(item for item in PRESET_DEFINITIONS if item.preset is preset)


class Phase3DemoService:
    def __init__(self, pdf_adapter_factory: PdfAdapterFactory | None = None) -> None:
        self._pdf_adapter_factory = pdf_adapter_factory or self._live_pdf_adapter

    def list_presets(self) -> list[dict[str, object]]:
        descriptions = []
        for definition in PRESET_DEFINITIONS:
            draft = demo_draft(definition.public_fact)
            bundle = build_phase3_preset(draft, definition.phase3_preset)
            descriptions.append(
                {
                    "id": definition.preset.value,
                    "title": definition.title,
                    "summary": definition.summary,
                    "plain_language_request": definition.plain_language_request,
                    "evidence_sources": [
                        {
                            "source_id": document.source.source_id,
                            "title": document.source.title,
                            "kind": document.kind.value,
                            "authority": document.authority.value,
                            "content": document.source.content,
                        }
                        for document in bundle.evidence_documents
                    ],
                }
            )
        return descriptions

    def new_pdf_adapter(self) -> PdfDocumentAdapter:
        """Create a backend-only adapter for document or audit PDF rendering."""

        return self._pdf_adapter_factory()

    @staticmethod
    def list_policy_profiles() -> list[dict[str, object]]:
        return [
            {
                "id": profile.id,
                "name": profile.name,
                "description": profile.description,
                "profile_hash": profile.profile_hash,
            }
            for profile in BUILT_IN_PROFILES.values()
        ]

    async def run(
        self,
        *,
        run_id: str,
        preset: DemoPreset,
        policy_profile: BuiltInPolicyProfile = BuiltInPolicyProfile.STANDARD_CONTRACT,
        output_path: Path,
        progress_observer: ProgressObserver,
    ) -> Phase3Result:
        definition = preset_definition(preset)
        draft = demo_draft(definition.public_fact)
        bundle = build_phase3_preset(draft, definition.phase3_preset)
        provider_name = os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").lower()
        if provider_name == "scripted":
            provider = bundle.scripted_provider
        elif provider_name == "openai":
            provider = OpenAIResponsesProvider.from_env()
        else:
            raise ValueError(f"Unsupported semantic provider: {provider_name}")

        workflow = Phase3Workflow(
            self._pdf_adapter_factory(),
            SemanticEngine(provider),
        )
        return await workflow.run(
            run_id=run_id,
            draft=draft,
            evidence_documents=bundle.evidence_documents,
            output_path=output_path,
            policy_profile=get_builtin_profile(policy_profile),
            progress_observer=progress_observer,
        )

    async def run_from_document(
        self,
        *,
        run_id: str,
        artifact_path: Path,
        evidence_documents: Sequence[EvidenceDocument],
        policy_profile: BuiltInPolicyProfile = BuiltInPolicyProfile.STANDARD_CONTRACT,
        output_path: Path,
        progress_observer: ProgressObserver,
    ) -> Phase3Result:
        """Verify a real, user-uploaded document against real, user-supplied
        evidence — no fixed preset, no scripted claims."""

        provider_name = os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").lower()
        if provider_name != "openai":
            raise RealDocumentReviewUnavailableError(
                "Document review requires a configured semantic provider. Set "
                "CLAIMGATE_SEMANTIC_PROVIDER=openai and OPENAI_API_KEY to enable it."
            )
        provider = OpenAIResponsesProvider.from_env()

        workflow = Phase3Workflow(
            self._pdf_adapter_factory(),
            SemanticEngine(provider),
        )
        return await workflow.run_from_document(
            run_id=run_id,
            pdf_path=artifact_path,
            evidence_documents=evidence_documents,
            output_path=output_path,
            policy_profile=get_builtin_profile(policy_profile),
            progress_observer=progress_observer,
        )

    @staticmethod
    def _live_pdf_adapter() -> PdfDocumentAdapter:
        return FoxitPdfClient(FoxitPdfSettings.from_env())


PROGRESS_LABELS = {
    Phase3Progress.GENERATING_DOCUMENT: "Generating document",
    Phase3Progress.READING_DOCUMENT: "Reading uploaded document",
    Phase3Progress.EXTRACTING_PDF: "Extracting final PDF",
    Phase3Progress.EXTRACTING_CLAIMS: "Extracting material claims",
    Phase3Progress.CHECKING_EVIDENCE: "Checking evidence",
    Phase3Progress.APPLYING_POLICY: "Applying deterministic policy",
}
