from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from claimgate.config import FoxitPdfSettings
from claimgate.integrations.foxit_pdf import FoxitPdfClient, FoxitPdfError


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name == "upload_document":
            payload = {"success": True, "documentId": "uploaded-html"}
        elif name == "pdf_from_html":
            payload = {"success": True, "resultDocumentId": "rendered-pdf"}
        elif name == "download_document":
            Path(arguments["outputPath"]).write_bytes(b"%PDF-1.7\nphase-zero")
            payload = {"success": True, "outputPath": arguments["outputPath"]}
        else:
            raise AssertionError(f"Unexpected tool: {name}")
        return SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(text=json.dumps(payload))],
        )


class FakeExtractionSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        if name == "upload_document":
            payload = {"success": True, "documentId": "uploaded-pdf"}
        elif name == "pdf_to_text":
            payload = {"success": True, "resultDocumentId": "extracted-text"}
        elif name == "download_document":
            Path(arguments["outputPath"]).write_text("Extracted agreement text")
            payload = {"success": True, "outputPath": arguments["outputPath"]}
        else:
            raise AssertionError(f"Unexpected tool: {name}")
        return SimpleNamespace(
            isError=False,
            content=[SimpleNamespace(text=json.dumps(payload))],
        )


@pytest.mark.asyncio
async def test_html_pipeline_is_strictly_allowlisted(tmp_path: Path) -> None:
    settings = FoxitPdfSettings("https://pdf.example", "id", "secret", tmp_path)
    client = FoxitPdfClient(settings)
    session = FakeSession()

    output = await client._generate_with_session(session, "<p>Hello</p>", tmp_path / "out.pdf")

    assert output.read_bytes().startswith(b"%PDF-")
    assert [name for name, _ in session.calls] == [
        "upload_document",
        "pdf_from_html",
        "download_document",
    ]


def test_launcher_bypasses_broken_foxit_main_module(tmp_path: Path) -> None:
    client = FoxitPdfClient(FoxitPdfSettings("https://pdf.example", "id", "secret", tmp_path))
    status_path = tmp_path / "status"

    params = client._server_parameters(status_path)

    assert params.command
    assert params.args == [
        "-m",
        "claimgate.integrations.foxit_mcp_launcher",
        str(tmp_path),
    ]
    assert "foxit_pdf_api_mcp_server.main" not in params.args
    assert params.env["CLAIMGATE_FOXIT_MCP_STATUS_PATH"] == str(status_path)


def test_nonzero_mcp_exit_is_not_accepted(tmp_path: Path) -> None:
    status_path = tmp_path / "status"
    status_path.write_text("1")

    with pytest.raises(FoxitPdfError, match="exited with status 1"):
        FoxitPdfClient._require_clean_exit(status_path)


@pytest.mark.asyncio
async def test_mcp_failure_is_reported(tmp_path: Path) -> None:
    class FailedSession:
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
            return SimpleNamespace(
                isError=False,
                content=[SimpleNamespace(text='{"success": false, "error": "bad credentials"}')],
            )

    client = FoxitPdfClient(FoxitPdfSettings("https://pdf.example", "id", "secret", tmp_path))
    with pytest.raises(FoxitPdfError, match="bad credentials"):
        await client._generate_with_session(FailedSession(), "<p>Hello</p>", tmp_path / "out.pdf")


@pytest.mark.asyncio
async def test_pdf_text_pipeline_is_strictly_allowlisted(tmp_path: Path) -> None:
    client = FoxitPdfClient(FoxitPdfSettings("https://pdf.example", "id", "secret", tmp_path))
    session = FakeExtractionSession()
    pdf_path = tmp_path / "agreement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nfixture")

    text = await client._extract_text_with_session(
        session,
        pdf_path,
        tmp_path / "agreement.txt",
    )

    assert text == "Extracted agreement text"
    assert [name for name, _ in session.calls] == [
        "upload_document",
        "pdf_to_text",
        "download_document",
    ]
