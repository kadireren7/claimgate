"""Vendor-neutral structured completion boundary with no tool capability."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import httpx


class ProviderError(RuntimeError):
    """Raised when a semantic provider cannot return a completed JSON object."""


class SemanticOperation(str, Enum):
    EXTRACT_CLAIMS = "extract_claims"
    VERIFY_EVIDENCE = "verify_evidence"


@dataclass(frozen=True)
class StructuredRequest:
    """A deliberately tool-free request passed to every semantic provider."""

    operation: SemanticOperation
    schema_name: str
    response_schema: Mapping[str, Any]
    developer_instructions: str
    untrusted_data: Mapping[str, Any]


class StructuredSemanticProvider(Protocol):
    async def complete_structured(self, request: StructuredRequest) -> object: ...


ScriptedResponse = object | Callable[[StructuredRequest], object]


class ScriptedSemanticProvider:
    """Deterministic fake used by tests and the credential-free demo preset."""

    def __init__(self, responses: Sequence[ScriptedResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[StructuredRequest] = []

    async def complete_structured(self, request: StructuredRequest) -> object:
        self.requests.append(request)
        if not self._responses:
            raise ProviderError("Scripted provider has no response for this request")
        response = self._responses.pop(0)
        return response(request) if callable(response) else response


class OpenAIResponsesProvider:
    """Optional OpenAI Responses adapter; no tools are included in its request."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key must not be empty")
        if not model.strip():
            raise ValueError("model must not be empty")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> OpenAIResponsesProvider:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        model = os.getenv("CLAIMGATE_OPENAI_MODEL", "").strip()
        if not api_key:
            raise ProviderError("OPENAI_API_KEY is required for the OpenAI provider")
        if not model:
            raise ProviderError("CLAIMGATE_OPENAI_MODEL is required for the OpenAI provider")
        return cls(
            api_key=api_key,
            model=model,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        )

    async def complete_structured(self, request: StructuredRequest) -> object:
        payload = self._build_payload(request)
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
                response = await client.post(
                    f"{self._base_url}/responses",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderError("OpenAI structured response request failed") from exc

        if body.get("status") != "completed":
            raise ProviderError(
                f"OpenAI response did not complete: {body.get('status', 'unknown')}"
            )
        output_text = self._find_output_text(body)
        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise ProviderError("OpenAI returned non-JSON output text") from exc
        if not isinstance(parsed, dict):
            raise ProviderError("OpenAI structured output was not a JSON object")
        return parsed

    def _build_payload(self, request: StructuredRequest) -> dict[str, Any]:
        return {
            "model": self._model,
            "store": False,
            "input": [
                {
                    "role": "developer",
                    "content": [
                        {"type": "input_text", "text": request.developer_instructions}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "UNTRUSTED_DATA_JSON\n"
                            + json.dumps(
                                request.untrusted_data,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ),
                        }
                    ],
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": request.schema_name,
                    "strict": True,
                    "schema": request.response_schema,
                }
            },
        }

    @staticmethod
    def _find_output_text(body: Mapping[str, Any]) -> str:
        for item in body.get("output", []):
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        return text
                if isinstance(content, dict) and content.get("type") == "refusal":
                    raise ProviderError("OpenAI refused the structured semantic request")
        raise ProviderError("OpenAI response contained no output_text")
