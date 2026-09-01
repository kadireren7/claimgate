"""Backend-only Foxit eSign REST client.

This module is intentionally independent of MCP and is never registered as an
agent tool. Calling ``send_pdf_for_signature`` creates and dispatches a real
Foxit eSign folder and is therefore reserved for an explicit human-approved path.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from claimgate.config import FoxitESignSettings


class FoxitESignError(RuntimeError):
    """Raised when Foxit eSign rejects a request or returns an invalid response."""


@dataclass(frozen=True)
class Signer:
    email: str
    first_name: str
    last_name: str


@dataclass(frozen=True)
class ESignSendResult:
    folder_id: str


class FoxitESignClient:
    """Minimal REST adapter kept outside the PDF MCP/agent boundary."""

    def __init__(
        self,
        settings: FoxitESignSettings,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._http = http_client or httpx.Client()
        self._owns_http_client = http_client is None

    def close(self) -> None:
        if self._owns_http_client:
            self._http.close()

    def __enter__(self) -> FoxitESignClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def send_pdf_for_signature(self, pdf_path: Path, signer: Signer) -> ESignSendResult:
        """Create a draft from a tagged PDF, then dispatch it to one signer.

        This operation is not idempotent. Call it once, only after explicit human approval.
        """
        self._validate_inputs(pdf_path, signer)
        token = self._get_access_token()
        folder_id = self._create_draft(pdf_path, signer, token)
        self._send_draft(folder_id, token)
        return ESignSendResult(folder_id=str(folder_id))

    def _get_access_token(self) -> str:
        response = self._http.post(
            f"{self._settings.base_url}/api/oauth2/access_token",
            data={
                "client_id": self._settings.client_id,
                "client_secret": self._settings.client_secret,
                "grant_type": "client_credentials",
                "scope": "read-write",
            },
            timeout=30,
        )
        self._raise_for_status(response, "OAuth token request")
        token = self._json_object(response, "OAuth token response").get("access_token")
        if not isinstance(token, str) or not token:
            raise FoxitESignError("Foxit OAuth response did not contain access_token")
        return token

    def _create_draft(self, pdf_path: Path, signer: Signer, token: str) -> str | int:
        encoded_pdf = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
        response = self._http.post(
            f"{self._settings.base_url}/api/folders/createfolder",
            headers=self._headers(token),
            json={
                "folderName": "ClaimGate Phase 0 Agreement",
                "inputType": "base64",
                "base64FileString": [encoded_pdf],
                "fileNames": [pdf_path.name],
                "processTextTags": True,
                "sendNow": False,
                "parties": [
                    {
                        "permission": "FILL_FIELDS_AND_SIGN",
                        "firstName": signer.first_name,
                        "lastName": signer.last_name,
                        "emailId": signer.email,
                        "sequence": 1,
                    }
                ],
            },
            timeout=60,
        )
        self._raise_for_status(response, "create folder request")
        payload = self._json_object(response, "create folder response")
        folder = payload.get("folder")
        folder_id = folder.get("folderId") if isinstance(folder, dict) else None
        if not isinstance(folder_id, (str, int)) or isinstance(folder_id, bool):
            raise FoxitESignError("Foxit create folder response did not contain folder.folderId")
        return folder_id

    def _send_draft(self, folder_id: str | int, token: str) -> None:
        response = self._http.post(
            f"{self._settings.base_url}/api/folders/sendDraftFolder",
            headers=self._headers(token),
            json={"folderId": folder_id},
            timeout=60,
        )
        self._raise_for_status(response, f"send draft request for folder {folder_id}")

    @staticmethod
    def _headers(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    @staticmethod
    def _json_object(response: httpx.Response, context: str) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FoxitESignError(f"{context} was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise FoxitESignError(f"{context} was not a JSON object")
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response, context: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise FoxitESignError(
                f"Foxit eSign {context} failed with HTTP {response.status_code}"
            ) from exc

    @staticmethod
    def _validate_inputs(pdf_path: Path, signer: Signer) -> None:
        if "@" not in signer.email or signer.email.startswith("@"):
            raise ValueError("Signer email is invalid")
        if not signer.first_name.strip() or not signer.last_name.strip():
            raise ValueError("Signer first and last name are required")
        if not pdf_path.is_file():
            raise FileNotFoundError(pdf_path)
        with pdf_path.open("rb") as pdf_file:
            if pdf_file.read(5) != b"%PDF-":
                raise ValueError(f"Not a PDF file: {pdf_path}")
