"""Run a sanitized live diagnostic against ClaimGate's exact extraction request."""

from __future__ import annotations

import asyncio
import difflib
import json
import os
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from claimgate.semantic.engine import (
    CLAIM_EXTRACTION_INSTRUCTIONS,
    _schema_with_string_enum,
)
from claimgate.semantic.models import ClaimExtractionPayload
from claimgate.semantic.provider import (
    OpenAIResponsesProvider,
    SemanticOperation,
    StructuredRequest,
)


async def main() -> None:
    load_dotenv(".env")
    extracted_text = Path("artifacts/web/6ec18a597f307e2821e58190.txt").read_text(
        encoding="utf-8"
    )
    source_lines = [line for line in extracted_text.splitlines() if line.strip()]
    request = StructuredRequest(
        operation=SemanticOperation.EXTRACT_CLAIMS,
        schema_name="claimgate_claim_extraction",
        response_schema=_schema_with_string_enum(
            ClaimExtractionPayload.model_json_schema(),
            definition="ExtractedClaim",
            property_name="source_text",
            allowed_values=source_lines,
        ),
        developer_instructions=CLAIM_EXTRACTION_INSTRUCTIONS,
        untrusted_data={
            "pdf_text": extracted_text,
            "source_lines": source_lines,
        },
    )
    provider = OpenAIResponsesProvider.from_env()
    payload = provider._build_payload(request)
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
            + "/responses",
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
    elapsed = time.monotonic() - started
    try:
        body = response.json()
    except ValueError:
        body = {}
    error = body.get("error") if isinstance(body, dict) else None
    error = error if isinstance(error, dict) else {}
    output_text = None
    parser_error = None
    claim_diagnostics = []
    if response.is_success and isinstance(body, dict):
        try:
            output_text = provider._find_output_text(body)
            parsed = ClaimExtractionPayload.model_validate(json.loads(output_text))
            lines = [line for line in extracted_text.splitlines() if line.strip()]
            for claim in parsed.claims:
                nearest = difflib.get_close_matches(claim.source_text, lines, n=1, cutoff=0.0)
                claim_diagnostics.append(
                    {
                        "claim_id": claim.claim_id,
                        "category": claim.category.value,
                        "normalized_value": claim.normalized_value,
                        "source_text": claim.source_text,
                        "exact_match": claim.source_text in extracted_text,
                        "nearest_extracted_line": nearest[0] if nearest else None,
                    }
                )
        except Exception as exc:  # diagnostic only: report type/message, never payload content
            parser_error = f"{type(exc).__name__}: {exc}"
    report = {
        "http_status": response.status_code,
        "elapsed_seconds": round(elapsed, 3),
        "openai_status": body.get("status") if isinstance(body, dict) else None,
        "error_type": error.get("type"),
        "error_code": error.get("code"),
        "error_message": error.get("message"),
        "response_id_present": bool(body.get("id")) if isinstance(body, dict) else False,
        "output_text_present": output_text is not None,
        "structured_validation_error": parser_error,
        "claim_diagnostics": claim_diagnostics,
        "schema_bytes": len(json.dumps(request.response_schema)),
        "untrusted_data_bytes": len(json.dumps(request.untrusted_data)),
    }
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
