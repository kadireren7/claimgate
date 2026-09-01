from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from claimgate.config import FoxitESignSettings
from claimgate.integrations.foxit_esign import FoxitESignClient, Signer


def test_esign_uses_token_draft_then_send(tmp_path: Path) -> None:
    pdf_path = tmp_path / "tagged.pdf"
    pdf_path.write_bytes(b"%PDF-1.7\ntagged-test")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/oauth2/access_token":
            assert request.headers["content-type"].startswith("application/x-www-form-urlencoded")
            return httpx.Response(200, json={"access_token": "test-token"})
        if request.url.path == "/api/folders/createfolder":
            payload = json.loads(request.content)
            assert payload["sendNow"] is False
            assert payload["processTextTags"] is True
            assert base64.b64decode(payload["base64FileString"][0]).startswith(b"%PDF-")
            assert payload["parties"][0]["emailId"] == "signer@example.com"
            return httpx.Response(200, json={"folder": {"folderId": 12345}})
        if request.url.path == "/api/folders/sendDraftFolder":
            assert json.loads(request.content) == {"folderId": 12345}
            return httpx.Response(200, json={"success": True})
        raise AssertionError(f"Unexpected request: {request.url}")

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    settings = FoxitESignSettings("https://esign.example", "client-id", "client-secret")
    client = FoxitESignClient(settings, http_client=http_client)

    result = client.send_pdf_for_signature(
        pdf_path,
        Signer("signer@example.com", "Test", "Signer"),
    )

    assert result.folder_id == "12345"
    assert [request.url.path for request in requests] == [
        "/api/oauth2/access_token",
        "/api/folders/createfolder",
        "/api/folders/sendDraftFolder",
    ]


def test_invalid_pdf_never_calls_esign(tmp_path: Path) -> None:
    not_pdf = tmp_path / "not.pdf"
    not_pdf.write_text("not a PDF")
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = FoxitESignClient(
        FoxitESignSettings("https://esign.example", "id", "secret"),
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    try:
        client.send_pdf_for_signature(not_pdf, Signer("signer@example.com", "Test", "Signer"))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid PDF to be rejected")
    assert called is False
