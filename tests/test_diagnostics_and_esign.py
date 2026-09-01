from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from claimgate.application import ApprovalSendService
from claimgate.config import ConfigurationError
from claimgate.integrations.foxit_esign import ESignSendResult, Signer
from claimgate.web.app import create_app
from claimgate.web.esign import LiveFoxitESignSender
from claimgate.web.service import Phase3DemoService


class FakeFoxitPdfAdapter:
    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\ntest-artifact")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        output_path.write_text("extracted text")
        return "extracted text"


class FakeESignSender:
    def __init__(self) -> None:
        self.calls: list[tuple[Path, Signer]] = []

    def send_pdf_for_signature(self, pdf_path: Path, signer: Signer) -> ESignSendResult:
        self.calls.append((pdf_path, signer))
        return ESignSendResult(folder_id="test-folder-1")


def build_test_app(tmp_path: Path, *, esign_sender: FakeESignSender | None = None):
    sender = esign_sender or FakeESignSender()
    app = create_app(
        demo_service=Phase3DemoService(lambda: FakeFoxitPdfAdapter()),
        approval_service=ApprovalSendService(sender),
        signer_factory=lambda: Signer("signer@example.com", "Test", "Signer"),
        artifact_directory=tmp_path / "web-artifacts",
    )
    app.state.test_esign_sender = sender
    return app


@pytest.mark.asyncio
async def test_diagnostics_endpoint_reports_booleans_and_no_secrets(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "foxit_pdf_configured",
        "foxit_esign_configured",
        "serpapi_configured",
        "semantic_provider",
        "public_evidence_provider",
        "live_sending_enabled",
    }
    assert isinstance(payload["foxit_pdf_configured"], bool)
    assert isinstance(payload["foxit_esign_configured"], bool)
    assert isinstance(payload["serpapi_configured"], bool)
    assert isinstance(payload["live_sending_enabled"], bool)
    serialized = str(payload)
    for secret_marker in ("client_secret", "CLIENT_SECRET", "api_key", "API_KEY", "Bearer"):
        assert secret_marker not in serialized


def test_diagnostics_snapshot_never_reads_actual_secret_values(monkeypatch) -> None:
    from claimgate.web.app import _diagnostics_snapshot

    monkeypatch.setenv("FOXIT_CLOUD_API_HOST", "https://example.invalid")
    monkeypatch.setenv("FOXIT_CLOUD_API_CLIENT_ID", "super-secret-client-id")
    monkeypatch.setenv("FOXIT_CLOUD_API_CLIENT_SECRET", "super-secret-client-secret")
    monkeypatch.setenv("FOXIT_PDF_MCP_DIRECTORY", "/tmp/does-not-matter")

    snapshot = _diagnostics_snapshot()

    assert snapshot["foxit_pdf_configured"] is True
    assert "super-secret-client-id" not in str(snapshot)
    assert "super-secret-client-secret" not in str(snapshot)


def test_live_foxit_esign_sender_requires_explicit_confirm_env(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("FOXIT_ESIGN_CONFIRM_SEND", raising=False)
    pdf_path = tmp_path / "agreement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\ntest")
    signer = Signer("signer@example.com", "Test", "Signer")

    with pytest.raises(ConfigurationError):
        LiveFoxitESignSender().send_pdf_for_signature(pdf_path, signer)

    monkeypatch.setenv("FOXIT_ESIGN_CONFIRM_SEND", "NO")
    with pytest.raises(ConfigurationError):
        LiveFoxitESignSender().send_pdf_for_signature(pdf_path, signer)
