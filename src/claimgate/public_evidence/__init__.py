"""Controlled supplementary public-evidence discovery."""

from claimgate.public_evidence.models import (
    PUBLIC_EVIDENCE_SNIPPET_MARKER,
    PublicEvidenceCandidate,
    PublicEvidenceDiscoveryResult,
    PublicEvidenceProviderResponse,
    PublicEvidenceQuery,
    PublicEvidenceSource,
    PublicFactType,
)
from claimgate.public_evidence.provider import (
    PublicEvidenceProvider,
    PublicEvidenceProviderError,
    ScriptedPublicEvidenceProvider,
)
from claimgate.public_evidence.serpapi import SerpApiPublicEvidenceProvider
from claimgate.public_evidence.service import (
    PublicEvidenceEnrichmentResult,
    PublicEvidenceService,
    canonicalize_url,
    classify_source,
)

__all__ = [
    "PublicEvidenceCandidate",
    "PublicEvidenceDiscoveryResult",
    "PublicEvidenceEnrichmentResult",
    "PublicEvidenceProvider",
    "PublicEvidenceProviderError",
    "PublicEvidenceProviderResponse",
    "PublicEvidenceQuery",
    "PublicEvidenceService",
    "PublicEvidenceSource",
    "PublicFactType",
    "PUBLIC_EVIDENCE_SNIPPET_MARKER",
    "ScriptedPublicEvidenceProvider",
    "SerpApiPublicEvidenceProvider",
    "canonicalize_url",
    "classify_source",
]
