from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
import pytest

from claimgate.application import Phase3Workflow
from claimgate.domain import PolicyOutcome, pdf_sha256
from claimgate.semantic import EvidenceIngestor, ScriptedSemanticProvider, SemanticEngine
from claimgate.web.app import create_app
from claimgate.web.service import Phase3DemoService, RealDocumentReviewUnavailableError

SIGNUP_PAYLOAD = {
    "full_name": "Ada Operator",
    "email": "ada@example.com",
    "workspace_name": "Ada's Workspace",
    "password": "correct horse battery",
    "confirm_password": "correct horse battery",
}

EXTRACTED_TEXT = (
    "Party name: Acme Corporation\n"
    "Contract amount: USD 12,500.00\n"
    "Quantity: 250\n"
    "Delivery date: 2026-09-30\n"
    "Scope: Istanbul pilot deployment\n"
    "Deliverable: 250 configured devices"
)
_CLAIMS = (
    ("party", "party_identity", "Acme Corporation", "Party name: Acme Corporation"),
    ("money", "money", "USD 12500.00", "Contract amount: USD 12,500.00"),
    ("quantity", "quantity", "250", "Quantity: 250"),
    ("delivery_date", "dates", "2026-09-30", "Delivery date: 2026-09-30"),
    ("scope", "scope", "Istanbul pilot deployment", "Scope: Istanbul pilot deployment"),
    (
        "deliverable",
        "deliverables",
        "250 configured devices",
        "Deliverable: 250 configured devices",
    ),
)
EXTRACTION = {
    "complete": True,
    "claims": [
        {
            "claim_id": claim_id,
            "category": category,
            "normalized_value": value,
            "source_text": source_text,
            "critical": True,
        }
        for claim_id, category, value, source_text in _CLAIMS
    ],
}


def supported_result() -> dict:
    return {
        "complete": True,
        "results": [
            {
                "claim_id": claim_id,
                "status": "SUPPORTED",
                "evidence_id": "evidence-1",
                "quotation": source_text,
                "notes": "Exact match",
            }
            for claim_id, _category, _value, source_text in _CLAIMS
        ],
    }


class FakeFoxitPdfAdapter:
    def __init__(self, extracted_text: str = EXTRACTED_TEXT) -> None:
        self.extracted_text = extracted_text
        self.calls: list[str] = []

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        self.calls.append("generate")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\nshould-not-be-called")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        self.calls.append("extract")
        output_path.write_text(self.extracted_text)
        return self.extracted_text


def build_app(tmp_path: Path, *, pdf_adapter_factory=None):
    service = Phase3DemoService(pdf_adapter_factory) if pdf_adapter_factory else None
    return create_app(
        demo_service=service,
        artifact_directory=tmp_path / "web-artifacts",
    )


async def _sign_up(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/auth/signup", json=SIGNUP_PAYLOAD)
    assert response.status_code == 201


async def _poll_run(client: httpx.AsyncClient, status_url: str) -> dict[str, object]:
    for _ in range(200):
        response = await client.get(status_url)
        payload = response.json()
        if payload["status"] != "running":
            return payload
        await asyncio.sleep(0.01)
    raise AssertionError("run did not complete in time")


@pytest.mark.asyncio
async def test_run_from_document_reuses_uploaded_pdf_bytes_and_skips_generation(
    tmp_path: Path,
) -> None:
    uploaded_pdf = tmp_path / "uploaded-contract.pdf"
    uploaded_pdf.write_bytes(b"%PDF-1.4\nreal-uploaded-contract-bytes")

    adapter = FakeFoxitPdfAdapter()
    evidence_documents = (
        EvidenceIngestor.plain_text(
            source_id="evidence-1",
            title="Purchase order",
            text=EXTRACTED_TEXT,
        ),
    )
    provider = ScriptedSemanticProvider([EXTRACTION, supported_result()])

    result = await Phase3Workflow(adapter, SemanticEngine(provider)).run_from_document(
        run_id="doc-run-1",
        pdf_path=uploaded_pdf,
        evidence_documents=evidence_documents,
        output_path=tmp_path / "doc-run-1.pdf",
        progress_observer=lambda progress: None,
    )

    assert adapter.calls == ["extract"]  # generation is skipped entirely
    assert result.pdf_path.read_bytes() == uploaded_pdf.read_bytes()
    assert result.decision.pdf_sha256 == pdf_sha256(uploaded_pdf.read_bytes())
    assert result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL


@pytest.mark.asyncio
async def test_service_run_from_document_fails_closed_without_real_provider(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("CLAIMGATE_SEMANTIC_PROVIDER", raising=False)
    service = Phase3DemoService(lambda: FakeFoxitPdfAdapter())
    uploaded_pdf = tmp_path / "uploaded.pdf"
    uploaded_pdf.write_bytes(b"%PDF-1.4\nsomething")

    with pytest.raises(RealDocumentReviewUnavailableError):
        await service.run_from_document(
            run_id="doc-run-2",
            artifact_path=uploaded_pdf,
            evidence_documents=(),
            output_path=tmp_path / "doc-run-2.pdf",
            progress_observer=lambda progress: None,
        )


@pytest.mark.asyncio
async def test_document_run_requires_session(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/runs/document",
            json={"artifact_upload_id": "missing", "evidence": [{"text": "x"}]},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_document_run_rejects_unknown_upload(tmp_path: Path) -> None:
    app = build_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        response = await client.post(
            "/api/runs/document",
            json={"artifact_upload_id": "does-not-exist", "evidence": [{"text": "x"}]},
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_document_run_fails_closed_when_provider_not_configured(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("CLAIMGATE_SEMANTIC_PROVIDER", raising=False)
    app = build_app(tmp_path, pdf_adapter_factory=lambda: FakeFoxitPdfAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        uploaded = await client.post(
            "/api/uploads",
            data={"kind": "artifact"},
            files={"file": ("contract.pdf", b"%PDF-1.4\nreal contract", "application/pdf")},
        )
        artifact_upload_id = uploaded.json()["upload_id"]

        started = await client.post(
            "/api/runs/document",
            json={
                "artifact_upload_id": artifact_upload_id,
                "evidence": [{"title": "Purchase order", "text": EXTRACTED_TEXT}],
            },
        )
        assert started.status_code == 202
        run = await _poll_run(client, started.json()["status_url"])

    assert run["status"] == "failed"
    assert "semantic provider" in run["error"].lower()


@pytest.mark.asyncio
async def test_document_run_reaches_decision_with_configured_provider(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("CLAIMGATE_SEMANTIC_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_provider = ScriptedSemanticProvider([EXTRACTION, supported_result()])
    monkeypatch.setattr(
        "claimgate.web.service.OpenAIResponsesProvider.from_env",
        staticmethod(lambda: fake_provider),
    )
    app = build_app(tmp_path, pdf_adapter_factory=lambda: FakeFoxitPdfAdapter())
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        await _sign_up(client)
        uploaded = await client.post(
            "/api/uploads",
            data={"kind": "artifact"},
            files={"file": ("contract.pdf", b"%PDF-1.4\nreal contract", "application/pdf")},
        )
        artifact_upload_id = uploaded.json()["upload_id"]

        started = await client.post(
            "/api/runs/document",
            json={
                "artifact_upload_id": artifact_upload_id,
                "evidence": [{"title": "Purchase order", "text": EXTRACTED_TEXT}],
            },
        )
        assert started.status_code == 202
        run = await _poll_run(client, started.json()["status_url"])

    assert run["status"] == "complete"
    assert run["preset_title"] == "contract.pdf"
    assert run["result"]["decision"] == "READY_FOR_HUMAN_APPROVAL"
