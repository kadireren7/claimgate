"""Run Phase 3 with live Foxit PDF operations and structured semantic verification."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from claimgate.application import (
    DraftDocument,
    Phase3Preset,
    Phase3Workflow,
    build_phase3_preset,
)
from claimgate.config import FoxitPdfSettings
from claimgate.domain import PolicyOutcome
from claimgate.integrations.foxit_pdf import FoxitPdfClient
from claimgate.policy_profiles import BuiltInPolicyProfile, get_builtin_profile
from claimgate.semantic import OpenAIResponsesProvider, SemanticEngine

DEFAULT_PHASE3_PDF = Path("artifacts/phase3-agreement.pdf")


def demo_draft() -> DraftDocument:
    return DraftDocument(
        party_name="Acme Corporation",
        contract_amount=Decimal("12500.00"),
        quantity=250,
        delivery_date=date(2026, 9, 30),
        scope="Istanbul pilot deployment",
        deliverable="250 configured devices",
    )


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ClaimGate Phase 3 safety demo")
    parser.add_argument(
        "--preset",
        type=str.lower,
        choices=[preset.value for preset in Phase3Preset],
        default=Phase3Preset.PASS.value,
    )
    parser.add_argument(
        "--provider",
        choices=("scripted", "openai"),
        default=os.getenv("CLAIMGATE_SEMANTIC_PROVIDER", "scripted").lower(),
        help="scripted is deterministic and needs no LLM credential",
    )
    parser.add_argument(
        "--policy-profile",
        choices=[profile.value for profile in BuiltInPolicyProfile],
        default=BuiltInPolicyProfile.STANDARD_CONTRACT.value,
        help="deterministic policy-as-code profile layered over the Phase 1 baseline",
    )
    return parser.parse_args()


async def _run(arguments: argparse.Namespace):
    load_dotenv()
    draft = demo_draft()
    preset = Phase3Preset(arguments.preset)
    bundle = build_phase3_preset(draft, preset)
    provider = (
        bundle.scripted_provider
        if arguments.provider == "scripted"
        else OpenAIResponsesProvider.from_env()
    )
    output = Path(os.getenv("CLAIMGATE_PHASE3_PDF", str(DEFAULT_PHASE3_PDF)))
    workflow = Phase3Workflow(
        FoxitPdfClient(FoxitPdfSettings.from_env()),
        SemanticEngine(provider),
    )
    return await workflow.run(
        run_id=f"phase3-{preset.value}-demo",
        draft=draft,
        evidence_documents=bundle.evidence_documents,
        output_path=output,
        policy_profile=get_builtin_profile(arguments.policy_profile),
    )


def main() -> None:
    result = asyncio.run(_run(_arguments()))
    statuses = {item.claim_id: item.status.value for item in result.verification.results}
    print("CLAIM_ID | CATEGORY | CRITICAL | STATUS | NORMALIZED_VALUE")
    for claim in result.extracted_claims:
        print(
            f"{claim.claim_id} | {claim.category.value} | "
            f"{'yes' if claim.critical else 'no'} | "
            f"{statuses.get(claim.claim_id, 'FAILED')} | {claim.normalized_value}"
        )
    decision_label = (
        "PASS"
        if result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
        else "BLOCK"
    )
    print(f"PDF={result.pdf_path}")
    print(f"PDF_SHA256={result.verification.pdf_sha256}")
    print(f"EVIDENCE_SHA256={result.verification.evidence_sha256}")
    print(f"POLICY_VERSION={result.decision.policy_version}")
    print(f"POLICY_PROFILE={result.selected_policy_profile.id}")
    print(f"POLICY_PROFILE_SHA256={result.selected_policy_profile.profile_hash}")
    print(f"BASELINE_DECISION={result.baseline_decision.outcome.value}")
    print(f"PROFILE_DECISION={result.profile_decision.outcome.value}")
    print(f"WORKFLOW_STATE={result.workflow.state.value}")
    print(f"DECISION={decision_label}")
    if result.semantic_failure:
        print(f"SEMANTIC_FAILURE={result.semantic_failure}")
    for blocker in result.decision.blockers:
        print(f"BLOCKER={blocker.code}: {blocker.message}")


if __name__ == "__main__":
    main()
