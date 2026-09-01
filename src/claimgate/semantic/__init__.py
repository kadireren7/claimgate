"""Structured semantic extraction and verification outside the policy boundary."""

from claimgate.semantic.engine import (
    SemanticEngine,
    SemanticOutputError,
    SemanticVerificationBundle,
)
from claimgate.semantic.evidence import EvidenceDocument, EvidenceIngestor, EvidenceKind
from claimgate.semantic.models import (
    EvidenceComparison,
    EvidenceComparisonPayload,
    ExtractedClaim,
    SemanticVerificationStatus,
)
from claimgate.semantic.provider import (
    OpenAIResponsesProvider,
    ProviderError,
    ScriptedSemanticProvider,
    SemanticOperation,
    StructuredRequest,
    StructuredSemanticProvider,
)

__all__ = [
    "EvidenceComparison",
    "EvidenceComparisonPayload",
    "EvidenceDocument",
    "EvidenceIngestor",
    "EvidenceKind",
    "ExtractedClaim",
    "OpenAIResponsesProvider",
    "ProviderError",
    "ScriptedSemanticProvider",
    "SemanticEngine",
    "SemanticOperation",
    "SemanticOutputError",
    "SemanticVerificationBundle",
    "SemanticVerificationStatus",
    "StructuredRequest",
    "StructuredSemanticProvider",
]
