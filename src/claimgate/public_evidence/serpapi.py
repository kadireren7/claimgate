"""Optional backend-only SerpApi Google organic-results adapter."""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone

import httpx

from claimgate.evidence_graph import EvidenceAuthority
from claimgate.public_evidence.models import PublicEvidenceQuery
from claimgate.public_evidence.provider import PublicEvidenceProviderError

SERPAPI_ENDPOINT = "https://serpapi.com/search"


class SerpApiPublicEvidenceProvider:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key.strip():
            raise ValueError("SerpApi api_key must not be empty")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    @classmethod
    def from_env(cls) -> SerpApiPublicEvidenceProvider:
        api_key = os.getenv("SERPAPI_API_KEY", "").strip()
        if not api_key:
            raise PublicEvidenceProviderError(
                "SERPAPI_API_KEY is required for live public evidence search"
            )
        return cls(api_key=api_key)

    async def search(self, query: PublicEvidenceQuery) -> object:
        params = {
            "engine": "google",
            "q": query.query,
            "api_key": self._api_key,
            "output": "json",
            "num": "5",
            "hl": "en",
            "safe": "active",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.get(SERPAPI_ENDPOINT, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise PublicEvidenceProviderError("SerpApi search request failed") from exc
        if not isinstance(payload, dict) or payload.get("error"):
            raise PublicEvidenceProviderError("SerpApi returned an invalid search response")
        organic_results = payload.get("organic_results", [])
        if not isinstance(organic_results, list):
            raise PublicEvidenceProviderError("SerpApi organic_results must be a list")
        search_metadata = payload.get("search_metadata", {})
        if not isinstance(search_metadata, dict):
            raise PublicEvidenceProviderError("SerpApi search_metadata must be an object")
        if search_metadata.get("status") != "Success":
            raise PublicEvidenceProviderError("SerpApi search did not complete successfully")

        retrieved_at = datetime.now(timezone.utc)
        candidates = []
        for item in organic_results[:5]:
            if not isinstance(item, dict):
                raise PublicEvidenceProviderError("SerpApi organic result is malformed")
            title = item.get("title")
            url = item.get("link")
            snippet = item.get("snippet")
            if not all(isinstance(value, str) and value.strip() for value in (title, url, snippet)):
                continue
            try:
                domain = httpx.URL(url).host
            except httpx.InvalidURL as exc:
                raise PublicEvidenceProviderError("SerpApi returned an invalid URL") from exc
            if domain is None:
                raise PublicEvidenceProviderError("SerpApi result URL has no domain")
            source_digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
            candidates.append(
                {
                    "source_id": f"public-{source_digest}",
                    "title": title,
                    "url": url,
                    "domain": domain.lower(),
                    "snippet": snippet,
                    "retrieved_at": retrieved_at,
                    "query": query.query,
                    "authority": EvidenceAuthority.UNVERIFIED_EXTERNAL.value,
                    "provider": "serpapi",
                    "provenance_metadata": {
                        "engine": "google",
                        "position": str(item.get("position", "unknown")),
                        "search_id": str(
                            search_metadata.get("id", "unknown")
                        ),
                    },
                }
            )
        return {"provider": "serpapi", "candidates": candidates}
