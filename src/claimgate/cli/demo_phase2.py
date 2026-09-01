"""Run the live Phase 2 PDF generation and deterministic verification demo."""

from __future__ import annotations

import asyncio
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from claimgate.application import DraftDocument, Phase2Workflow
from claimgate.config import FoxitPdfSettings
from claimgate.domain import PolicyOutcome
from claimgate.integrations.foxit_pdf import FoxitPdfClient

DEFAULT_PHASE2_PDF = Path("artifacts/phase2-agreement.pdf")


def demo_draft() -> DraftDocument:
    return DraftDocument(
        party_name="Acme Corporation",
        contract_amount=Decimal("12500.00"),
        quantity=250,
        delivery_date=date(2026, 9, 30),
        scope="Istanbul pilot deployment",
        deliverable="250 configured devices",
    )


async def _run():
    load_dotenv()
    output = Path(os.getenv("CLAIMGATE_PHASE2_PDF", str(DEFAULT_PHASE2_PDF)))
    workflow = Phase2Workflow(FoxitPdfClient(FoxitPdfSettings.from_env()))
    return await workflow.run(
        run_id="phase2-live-demo",
        draft=demo_draft(),
        output_path=output,
    )


def main() -> None:
    result = asyncio.run(_run())
    decision_label = (
        "PASS"
        if result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
        else "BLOCK"
    )
    print(f"PDF={result.pdf_path}")
    print(f"EXTRACTED_TEXT={result.extracted_text_path}")
    print(f"PDF_SHA256={result.verification.pdf_sha256}")
    print(f"EVIDENCE_SHA256={result.verification.evidence_sha256}")
    print(f"POLICY_VERSION={result.decision.policy_version}")
    print(f"WORKFLOW_STATE={result.workflow.state.value}")
    print(f"DECISION={decision_label}")
    for blocker in result.decision.blockers:
        print(f"BLOCKER={blocker.code}: {blocker.message}")


if __name__ == "__main__":
    main()
