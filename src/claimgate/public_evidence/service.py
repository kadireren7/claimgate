"""Controlled discovery, deterministic trust classification, and deduplication."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import ValidationError

from claimgate.application import Phase3Result
from claimgate.domain import (
    ClaimCategory,
    DeterministicPolicyEngine,
    VerificationSnapshot,
    VerificationStatus,
    WorkflowRun,
    evidence_sha256,
    pdf_sha256,
)
from claimgate.evidence_graph import EvidenceAuthority, EvidenceSourceType
from claimgate.evidence_graph.builder import build_evidence_graph
from claimgate.policy_profiles import PolicyEvaluationContext, PolicyProfileEvaluator
from claimgate.public_evidence.models import (
    PublicEvidenceDiscoveryResult,
    PublicEvidenceProviderResponse,
    PublicEvidenceQuery,
    PublicEvidenceSource,
    PublicFactType,
)
from claimgate.public_evidence.provider import (
    PublicEvidenceProvider,
    PublicEvidenceProviderError,
)
from claimgate.semantic import (
    ExtractedClaim,
    SemanticEngine,
    SemanticOutputError,
    SemanticVerificationStatus,
)


@dataclass(frozen=True)
class PublicEvidenceEnrichmentResult:
    result: Phase3Result
    discovery: PublicEvidenceDiscoveryResult
    previous_status: VerificationStatus
    current_status: VerificationStatus
    reevaluated: bool

GOVERNMENT_SUFFIXES = (".gov", ".gov.tr", ".gc.ca", ".gov.uk", ".europa.eu")
CERTIFICATION_REGISTRIES = frozenset(
    {"iafcertsearch.org", "www.iafcertsearch.org", "iso.org", "www.iso.org"}
)
ESTABLISHED_THIRD_PARTIES = frozenset(
    {"reuters.com", "www.reuters.com", "bloomberg.com", "www.bloomberg.com"}
)
TRACKING_PARAMETERS = frozenset(
    {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid"}
)


class PublicEvidenceService:
    def __init__(self, provider: PublicEvidenceProvider) -> None:
        self._provider = provider

    @staticmethod
    def build_query(
        claim: ExtractedClaim,
        *,
        fact_type: PublicFactType,
        official_domains: tuple[str, ...] = (),
    ) -> PublicEvidenceQuery:
        if not _eligible(claim.category, fact_type):
            raise ValueError(
                f"Public search is not eligible for category {claim.category.value}"
            )
        normalized = re.sub(
            r"[^\w\s.,&()/-]",
            " ",
            " ".join(claim.normalized_value.split()),
        )
        normalized = " ".join(normalized.split())[:300]
        if not normalized:
            raise ValueError("Public search claim contains no allowlisted query text")
        query = f'"{normalized}"'
        return PublicEvidenceQuery(
            claim_id=claim.claim_id,
            claim_category=claim.category,
            fact_type=fact_type,
            normalized_claim=normalized,
            query=query,
            official_domains=official_domains,
        )

    async def discover(
        self,
        claim: ExtractedClaim,
        *,
        fact_type: PublicFactType,
        official_domains: tuple[str, ...] = (),
    ) -> PublicEvidenceDiscoveryResult:
        try:
            query = self.build_query(
                claim,
                fact_type=fact_type,
                official_domains=official_domains,
            )
        except ValueError as exc:
            return PublicEvidenceDiscoveryResult(
                query=None,
                provider=type(self._provider).__name__,
                eligible=False,
                searched=False,
                succeeded=False,
                sources=(),
                blocker_codes=("PUBLIC_SEARCH_INELIGIBLE",),
                message=str(exc),
            )
        try:
            raw = await self._provider.search(query)
            response = PublicEvidenceProviderResponse.model_validate(raw)
            sources = self._accept_sources(query, response)
        except (PublicEvidenceProviderError, ValidationError, ValueError, TypeError):
            return PublicEvidenceDiscoveryResult(
                query=query,
                provider=type(self._provider).__name__,
                eligible=True,
                searched=True,
                succeeded=False,
                sources=(),
                blocker_codes=("PUBLIC_EVIDENCE_PROVIDER_INVALID",),
                message="Public evidence provider output failed strict validation.",
            )
        return PublicEvidenceDiscoveryResult(
            query=query,
            provider=response.provider,
            eligible=True,
            searched=True,
            succeeded=True,
            sources=sources,
            message=f"Discovered {len(sources)} deduplicated public evidence source(s).",
        )

    async def enrich_result(
        self,
        *,
        result: Phase3Result,
        claim_id: str,
        fact_type: PublicFactType,
        semantic_engine: SemanticEngine,
        official_domains: tuple[str, ...] = (),
    ) -> PublicEvidenceEnrichmentResult:
        extracted_claim = next(
            (claim for claim in result.extracted_claims if claim.claim_id == claim_id),
            None,
        )
        verification = next(
            (item for item in result.verification.results if item.claim_id == claim_id),
            None,
        )
        if extracted_claim is None or verification is None:
            raise ValueError("Public evidence claim is not part of this verified run")
        if verification.status not in {
            VerificationStatus.UNSUPPORTED,
            VerificationStatus.UNCERTAIN,
        }:
            raise ValueError("Public evidence is limited to unsupported or uncertain claims")

        discovery = await self.discover(
            extracted_claim,
            fact_type=fact_type,
            official_domains=official_domains,
        )
        if not discovery.succeeded or not discovery.sources:
            return PublicEvidenceEnrichmentResult(
                result=result,
                discovery=discovery,
                previous_status=verification.status,
                current_status=verification.status,
                reevaluated=False,
            )

        public_documents = tuple(
            source.to_evidence_document() for source in discovery.sources
        )
        all_documents = (*result.evidence_documents, *public_documents)
        all_evidence = tuple(document.source for document in all_documents)
        current_pdf_hash = pdf_sha256(result.pdf_path.read_bytes())
        current_evidence_hash = evidence_sha256(all_evidence)
        try:
            public_bundle = await semantic_engine.verify_evidence_bundle(
                claims=(extracted_claim,),
                evidence=tuple(document.source for document in public_documents),
                verified_pdf_sha256=current_pdf_hash,
                verified_evidence_sha256=current_evidence_hash,
            )
        except SemanticOutputError:
            failed_discovery = discovery.model_copy(
                update={
                    "succeeded": False,
                    "blocker_codes": ("PUBLIC_EVIDENCE_COMPARISON_INVALID",),
                    "message": "Public evidence comparison failed strict semantic validation.",
                }
            )
            return PublicEvidenceEnrichmentResult(
                result=result,
                discovery=failed_discovery,
                previous_status=verification.status,
                current_status=verification.status,
                reevaluated=False,
            )

        retained_comparisons = tuple(
            comparison
            for comparison in result.semantic_comparisons
            if not (
                comparison.claim_id == claim_id
                and comparison.status
                in {
                    SemanticVerificationStatus.UNSUPPORTED,
                    SemanticVerificationStatus.UNCERTAIN,
                }
            )
        )
        comparisons = (*retained_comparisons, *public_bundle.comparisons)
        verification_results = SemanticEngine.project_policy_results(
            result.extracted_claims, comparisons
        )
        snapshot = VerificationSnapshot(
            pdf_sha256=current_pdf_hash,
            evidence_sha256=current_evidence_hash,
            results=verification_results,
        )
        graph = build_evidence_graph(
            claims=result.extracted_claims,
            evidence_documents=all_documents,
            comparisons=comparisons,
        )
        baseline = DeterministicPolicyEngine().evaluate(
            claims=result.claims,
            evidence=all_evidence,
            verification=snapshot,
            current_pdf_sha256=current_pdf_hash,
        )
        effective = PolicyProfileEvaluator().evaluate(
            PolicyEvaluationContext(
                baseline_decision=baseline,
                selected_profile=result.selected_policy_profile,
                evidence_graph=graph,
            )
        )
        workflow = WorkflowRun(result.workflow.run_id)
        workflow.start_generation()
        workflow.start_verification(
            pdf_sha256=current_pdf_hash,
            evidence_sha256=current_evidence_hash,
        )
        workflow.apply_policy(effective.final_decision)
        updated = replace(
            result,
            workflow=workflow,
            evidence_documents=all_documents,
            evidence=all_evidence,
            verification=snapshot,
            semantic_comparisons=comparisons,
            evidence_graph=graph,
            baseline_decision=baseline,
            profile_decision=effective.profile_decision,
            decision=effective.final_decision,
        )
        updated_status = next(
            item.status for item in snapshot.results if item.claim_id == claim_id
        )
        return PublicEvidenceEnrichmentResult(
            result=updated,
            discovery=discovery,
            previous_status=verification.status,
            current_status=updated_status,
            reevaluated=True,
        )

    @staticmethod
    def _accept_sources(
        query: PublicEvidenceQuery,
        response: PublicEvidenceProviderResponse,
    ) -> tuple[PublicEvidenceSource, ...]:
        accepted: list[PublicEvidenceSource] = []
        seen_urls: set[str] = set()
        seen_domains: set[str] = set()
        seen_source_ids: set[str] = set()
        seen_provider_source_ids: set[str] = set()
        for candidate in response.candidates:
            canonical_url = canonicalize_url(candidate.url)
            domain = (urlsplit(canonical_url).hostname or "").lower()
            source_type, authority = classify_source(
                domain,
                official_domains=query.official_domains,
            )
            source_id = "public-" + hashlib.sha256(
                canonical_url.encode("utf-8")
            ).hexdigest()[:16]
            if (
                canonical_url in seen_urls
                or domain in seen_domains
                or source_id in seen_source_ids
                or candidate.source_id in seen_provider_source_ids
            ):
                continue
            seen_urls.add(canonical_url)
            seen_domains.add(domain)
            seen_source_ids.add(source_id)
            seen_provider_source_ids.add(candidate.source_id)
            accepted.append(
                PublicEvidenceSource(
                    source_id=source_id,
                    title=candidate.title,
                    url=candidate.url,
                    canonical_url=canonical_url,
                    domain=domain,
                    snippet=candidate.snippet,
                    retrieved_at=candidate.retrieved_at,
                    query=query.query,
                    authority=authority,
                    source_type=source_type,
                    provider=response.provider,
                    provenance_metadata=candidate.provenance_metadata,
                )
            )
        return tuple(sorted(accepted, key=lambda source: source.source_id))


def classify_source(
    domain: str,
    *,
    official_domains: tuple[str, ...] = (),
) -> tuple[EvidenceSourceType, EvidenceAuthority]:
    normalized = domain.lower().rstrip(".")
    if normalized in official_domains:
        return (
            EvidenceSourceType.OFFICIAL_ORGANIZATION_DOMAIN,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    if any(normalized.endswith(suffix) for suffix in GOVERNMENT_SUFFIXES):
        return (
            EvidenceSourceType.GOVERNMENT_REGULATOR,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    if normalized in CERTIFICATION_REGISTRIES:
        return (
            EvidenceSourceType.CERTIFICATION_REGISTRY,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    if normalized in ESTABLISHED_THIRD_PARTIES:
        return (
            EvidenceSourceType.ESTABLISHED_THIRD_PARTY,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        )
    return (
        EvidenceSourceType.UNKNOWN_THIRD_PARTY,
        EvidenceAuthority.UNVERIFIED_EXTERNAL,
    )


def canonicalize_url(url: str) -> str:
    parsed = urlsplit(url)
    query = urlencode(
        sorted(
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if key.lower() not in TRACKING_PARAMETERS
        )
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), path, query, "")
    )


def _eligible(category: ClaimCategory, fact_type: PublicFactType) -> bool:
    if category is ClaimCategory.PARTY_IDENTITY:
        return fact_type in {
            PublicFactType.PARTY_IDENTITY,
            PublicFactType.PUBLIC_COMPANY_INFORMATION,
        }
    if category is ClaimCategory.OTHER:
        return fact_type in {
            PublicFactType.CERTIFICATION_STATUS,
            PublicFactType.PUBLIC_COMPANY_INFORMATION,
            PublicFactType.PRODUCT_SPECIFICATION,
        }
    return False
