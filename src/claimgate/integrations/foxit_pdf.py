"""Tiny allowlisted client for the official Foxit PDF MCP server."""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Protocol

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from claimgate.config import FoxitPdfSettings
from claimgate.extraction import estimate_pdf_page_count


class FoxitPdfError(RuntimeError):
    """Raised when the MCP server or Foxit PDF Services rejects an operation."""


class _ToolSession(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...


class FoxitPdfClient:
    """Allowlisted HTML-to-PDF and PDF-to-text Foxit MCP pipelines."""

    def __init__(self, settings: FoxitPdfSettings) -> None:
        self._settings = settings
        self._ocr_outputs: set[Path] = set()

    def extraction_used_ocr(self, output_path: Path) -> bool:
        return output_path.expanduser().resolve() in self._ocr_outputs

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        """Upload fixed HTML, convert it, and download the resulting PDF."""
        if not html.strip():
            raise ValueError("HTML must not be empty")

        with tempfile.TemporaryDirectory(prefix="claimgate-foxit-mcp-") as temp_directory:
            status_path = Path(temp_directory) / "exit-status"
            async with stdio_client(self._server_parameters(status_path)) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    output = await self._generate_with_session(session, html, output_path)
            self._require_clean_exit(status_path)
            return output

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        """Upload the generated PDF, convert it to text, and return the extracted text."""
        resolved_pdf = pdf_path.expanduser().resolve()
        self._validate_pdf(resolved_pdf)

        with tempfile.TemporaryDirectory(prefix="claimgate-foxit-mcp-") as temp_directory:
            status_path = Path(temp_directory) / "exit-status"
            async with stdio_client(self._server_parameters(status_path)) as (
                read_stream,
                write_stream,
            ):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    text = await self._extract_text_with_session(
                        session,
                        resolved_pdf,
                        output_path,
                    )
            self._require_clean_exit(status_path)
            return text

    def _server_parameters(self, status_path: Path) -> StdioServerParameters:
        """Launch Foxit's server object through FastMCP's supported synchronous CLI.

        The pinned Foxit revision's ``main.py`` incorrectly calls
        ``asyncio.run(mcp.run())`` even though FastMCP 2.x ``run()`` is synchronous.
        A package-aware compatibility launcher calls ``mcp.run()`` synchronously,
        avoiding any upstream edit while preserving clean startup and shutdown.
        """
        child_environment = os.environ.copy()
        child_environment.pop("VIRTUAL_ENV", None)
        child_environment.update(
            {
                "CLAIMGATE_FOXIT_MCP_STATUS_PATH": str(status_path),
                "FOXIT_CLOUD_API_HOST": self._settings.api_host,
                "FOXIT_CLOUD_API_CLIENT_ID": self._settings.client_id,
                "FOXIT_CLOUD_API_CLIENT_SECRET": self._settings.client_secret,
            }
        )
        return StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                "claimgate.integrations.foxit_mcp_launcher",
                str(self._settings.mcp_directory),
            ],
            env=child_environment,
        )

    @staticmethod
    def _require_clean_exit(status_path: Path) -> None:
        try:
            raw_status = status_path.read_text(encoding="utf-8").strip()
            status = int(raw_status)
        except (OSError, ValueError) as exc:
            raise FoxitPdfError("Foxit MCP process did not report a clean exit status") from exc
        if status != 0:
            raise FoxitPdfError(f"Foxit MCP process exited with status {status}")

    async def _generate_with_session(
        self, session: _ToolSession, html: str, output_path: Path
    ) -> Path:
        upload = await self._call_json(
            session,
            "upload_document",
            {
                "fileContent": base64.b64encode(html.encode("utf-8")).decode("ascii"),
                "fileName": "claimgate-phase0.html",
            },
        )
        document_id = self._field(upload, "documentId", "upload_document")

        conversion = await self._call_json(
            session,
            "pdf_from_html",
            {"documentId": document_id},
        )
        result_document_id = self._field(conversion, "resultDocumentId", "pdf_from_html")

        resolved_output = output_path.expanduser().resolve()
        await self._call_json(
            session,
            "download_document",
            {
                "documentId": result_document_id,
                "outputPath": str(resolved_output),
                "filename": resolved_output.name,
            },
        )
        self._validate_pdf(resolved_output)
        return resolved_output

    async def _extract_text_with_session(
        self,
        session: _ToolSession,
        pdf_path: Path,
        output_path: Path,
    ) -> str:
        upload = await self._call_json(
            session,
            "upload_document",
            {
                "fileContent": base64.b64encode(pdf_path.read_bytes()).decode("ascii"),
                "fileName": pdf_path.name,
            },
        )
        document_id = self._field(upload, "documentId", "upload_document")

        conversion = await self._call_json(
            session,
            "pdf_to_text",
            {"documentId": document_id},
        )
        result_document_id = self._field(
            conversion,
            "resultDocumentId",
            "pdf_to_text",
        )

        resolved_output = output_path.expanduser().resolve()
        extracted_text = await self._download_text(
            session,
            result_document_id,
            resolved_output,
        )
        minimum_ocr_density = estimate_pdf_page_count(pdf_path) * 20
        if sum(not character.isspace() for character in extracted_text) < minimum_ocr_density:
            ocr = await self._call_json(
                session,
                "pdf_ocr",
                {
                    "documentId": document_id,
                    "languages": ["en-US", "tr-TR"],
                },
            )
            searchable_pdf_id = self._field(ocr, "resultDocumentId", "pdf_ocr")
            ocr_conversion = await self._call_json(
                session,
                "pdf_to_text",
                {"documentId": searchable_pdf_id},
            )
            ocr_text_id = self._field(
                ocr_conversion,
                "resultDocumentId",
                "pdf_to_text",
            )
            extracted_text = await self._download_text(
                session,
                ocr_text_id,
                resolved_output,
            )
            self._ocr_outputs.add(resolved_output)
        else:
            self._ocr_outputs.discard(resolved_output)
        return extracted_text

    async def _download_text(
        self,
        session: _ToolSession,
        document_id: str,
        output_path: Path,
    ) -> str:
        await self._call_json(
            session,
            "download_document",
            {
                "documentId": document_id,
                "outputPath": str(output_path),
                "filename": output_path.name,
            },
        )
        try:
            extracted_text = output_path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise FoxitPdfError(
                f"Foxit text output could not be read as UTF-8: {output_path}"
            ) from exc
        return extracted_text

    @staticmethod
    async def _call_json(
        session: _ToolSession, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        result = await session.call_tool(tool_name, arguments=arguments)
        if getattr(result, "isError", False):
            raise FoxitPdfError(f"MCP tool {tool_name} returned an error")

        text_blocks = [
            block.text for block in getattr(result, "content", []) if hasattr(block, "text")
        ]
        if not text_blocks:
            raise FoxitPdfError(f"MCP tool {tool_name} returned no JSON text")
        try:
            payload = json.loads(text_blocks[0])
        except json.JSONDecodeError as exc:
            raise FoxitPdfError(f"MCP tool {tool_name} returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise FoxitPdfError(f"MCP tool {tool_name} returned a non-object payload")
        if payload.get("success") is not True:
            detail = payload.get("error", "unknown Foxit error")
            raise FoxitPdfError(f"MCP tool {tool_name} failed: {detail}")
        return payload

    @staticmethod
    def _field(payload: dict[str, Any], name: str, tool_name: str) -> str:
        value = payload.get(name)
        if not isinstance(value, str) or not value:
            raise FoxitPdfError(f"MCP tool {tool_name} did not return {name}")
        return value

    @staticmethod
    def _validate_pdf(path: Path) -> None:
        if not path.is_file() or path.stat().st_size < 5:
            raise FoxitPdfError(f"Foxit did not create a PDF at {path}")
        with path.open("rb") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise FoxitPdfError(f"Downloaded artifact is not a PDF: {path}")
