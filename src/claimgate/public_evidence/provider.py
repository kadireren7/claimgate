"""Vendor-neutral public search provider boundary and deterministic fake."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from claimgate.public_evidence.models import PublicEvidenceQuery


class PublicEvidenceProviderError(RuntimeError):
    """Raised when a provider cannot safely return structured search results."""


class PublicEvidenceProvider(Protocol):
    async def search(self, query: PublicEvidenceQuery) -> object: ...


ScriptedSearchResponse = object | Callable[[PublicEvidenceQuery], object]


class ScriptedPublicEvidenceProvider:
    def __init__(self, responses: Sequence[ScriptedSearchResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[PublicEvidenceQuery] = []

    async def search(self, query: PublicEvidenceQuery) -> object:
        self.requests.append(query)
        if not self._responses:
            raise PublicEvidenceProviderError(
                "Scripted public evidence provider has no response"
            )
        response = self._responses.pop(0)
        return response(query) if callable(response) else response

