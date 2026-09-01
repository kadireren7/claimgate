from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from claimgate.application import (
    Phase3Preset,
    Phase3Workflow,
    build_phase3_preset,
    build_sign_document_action,
)
from claimgate.audit import ReceiptESignStatus, ReceiptESignSummary, issue_decision_receipt
from claimgate.domain import ClaimCategory, PolicyOutcome, VerificationStatus, evidence_sha256
from claimgate.evidence_graph import EvidenceAuthority, EvidenceSourceType
from claimgate.policy_profiles import PUBLIC_EVIDENCE_STRICT
from claimgate.public_evidence import (
    PUBLIC_EVIDENCE_SNIPPET_MARKER,
    PublicEvidenceService,
    PublicFactType,
    ScriptedPublicEvidenceProvider,
    SerpApiPublicEvidenceProvider,
    classify_source,
)
from claimgate.replay import (
    ReplayRequest,
    ReplayStatus,
    ReplayVerifier,
    capture_artifact_snapshot,
)
from claimgate.semantic import ExtractedClaim, ScriptedSemanticProvider, SemanticEngine

FIXED_TIME = datetime(2026, 8, 19, 15, 0, tzinfo=timezone.utc)
PUBLIC_FACT = "Example organization holds Certification X"
EXTRACTED_PUBLIC_AGREEMENT = f"""ClaimGate Controlled Agreement
Party name: Acme Corporation
Contract amount: USD 12,500.00
Quantity: 250
Delivery date: 2026-09-30
Scope: Istanbul pilot deployment
Deliverable: 250 configured devices
Public status: {PUBLIC_FACT}
"""


@pytest.mark.parametrize(
    ("domain", "official_domains", "expected_type", "expected_authority"),
    [
        (
            "example.org",
            ("example.org",),
            EvidenceSourceType.OFFICIAL_ORGANIZATION_DOMAIN,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        ),
        (
            "registry.sec.gov",
            (),
            EvidenceSourceType.GOVERNMENT_REGULATOR,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        ),
        (
            "iafcertsearch.org",
            (),
            EvidenceSourceType.CERTIFICATION_REGISTRY,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        ),
        (
            "reuters.com",
            (),
            EvidenceSourceType.ESTABLISHED_THIRD_PARTY,
            EvidenceAuthority.VERIFIED_EXTERNAL,
        ),
        (
            "unknown.example",
            (),
            EvidenceSourceType.UNKNOWN_THIRD_PARTY,
            EvidenceAuthority.UNVERIFIED_EXTERNAL,
        ),
    ],
)
def test_source_trust_classification_is_deterministic(
    domain: str,
    official_domains: tuple[str, ...],
    expected_type: EvidenceSourceType,
    expected_authority: EvidenceAuthority,
) -> None:
    assert classify_source(domain, official_domains=official_domains) == (
        expected_type,
        expected_authority,
    )


class PublicEvidencePdfAdapter:
    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        assert PUBLIC_FACT in html
        output_path.write_bytes(b"%PDF-1.4\npublic-evidence")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        output_path.write_text(EXTRACTED_PUBLIC_AGREEMENT, encoding="utf-8")
        return EXTRACTED_PUBLIC_AGREEMENT


def search_response(
    *,
    domain: str,
    snippet: str = PUBLIC_FACT,
    url_suffix: str = "record",
    authority: str = "UNVERIFIED_EXTERNAL",
    duplicate: bool = False,
    retrieved_at: datetime = FIXED_TIME,
):
    def response(query):
        candidates = [
            {
                "source_id": "provider-result-1",
                "title": "Certification record",
                "url": f"https://{domain}/{url_suffix}?utm_source=search",
                "domain": domain,
                "snippet": snippet,
                "retrieved_at": retrieved_at,
                "query": query.query,
                "authority": authority,
                "provider": "scripted-search",
                "provenance_metadata": {"position": "1"},
            }
        ]
        if duplicate:
            candidates.append(
                {
                    **candidates[0],
                    "source_id": "provider-result-duplicate",
                    "url": f"https://{domain}/{url_suffix}?utm_medium=duplicate",
                }
            )
        return {"provider": "scripted-search", "candidates": candidates}

    return response


def semantic_comparator() -> SemanticEngine:
    def response(request):
        results = []
        for claim in request.untrusted_data["claims"]:
            for source in request.untrusted_data["evidence_sources"]:
                content = str(source["content"])
                quotation = content.split(PUBLIC_EVIDENCE_SNIPPET_MARKER, 1)[-1]
                results.append(
                    {
                        "claim_id": claim["claim_id"],
                        "status": (
                            "SUPPORTED"
                            if str(claim["normalized_value"]).casefold()
                            in content.casefold()
                            else "UNCERTAIN"
                        ),
                        "evidence_id": source["source_id"],
                        "quotation": quotation,
                        "notes": "Controlled public evidence comparison",
                    }
                )
        return {"complete": True, "results": results}

    return SemanticEngine(ScriptedSemanticProvider([response]))


async def initial_public_result(tmp_path: Path, draft):
    public_draft = replace(draft, public_fact=PUBLIC_FACT)
    bundle = build_phase3_preset(public_draft, Phase3Preset.PUBLIC_CLAIM)
    return await Phase3Workflow(
        PublicEvidencePdfAdapter(), SemanticEngine(bundle.scripted_provider)
    ).run(
        run_id="public-evidence-run",
        draft=public_draft,
        evidence_documents=bundle.evidence_documents,
        output_path=tmp_path / "public-evidence.pdf",
        policy_profile=PUBLIC_EVIDENCE_STRICT,
    )


@pytest.mark.asyncio
async def test_public_search_can_never_create_authoritative_internal_evidence() -> None:
    provider = ScriptedPublicEvidenceProvider(
        [search_response(domain="iafcertsearch.org", authority="AUTHORITATIVE_INTERNAL")]
    )
    claim = ExtractedClaim(
        claim_id="certification",
        category=ClaimCategory.OTHER,
        normalized_value=PUBLIC_FACT,
        source_text=f"Public status: {PUBLIC_FACT}",
        critical=False,
    )

    discovery = await PublicEvidenceService(provider).discover(
        claim, fact_type=PublicFactType.CERTIFICATION_STATUS
    )

    assert discovery.succeeded is False
    assert discovery.sources == ()
    assert discovery.blocker_codes == ("PUBLIC_EVIDENCE_PROVIDER_INVALID",)


@pytest.mark.asyncio
async def test_private_money_claim_is_never_auto_searched() -> None:
    provider = ScriptedPublicEvidenceProvider([{}])
    money = ExtractedClaim(
        claim_id="money",
        category=ClaimCategory.MONEY,
        normalized_value="USD 12500.00",
        source_text="Contract amount: USD 12,500.00",
        critical=True,
    )

    discovery = await PublicEvidenceService(provider).discover(
        money, fact_type=PublicFactType.PUBLIC_COMPANY_INFORMATION
    )

    assert discovery.eligible is False
    assert discovery.searched is False
    assert discovery.blocker_codes == ("PUBLIC_SEARCH_INELIGIBLE",)
    assert provider.requests == []


@pytest.mark.asyncio
async def test_duplicate_urls_are_canonicalized_and_deduplicated() -> None:
    provider = ScriptedPublicEvidenceProvider(
        [search_response(domain="iafcertsearch.org", duplicate=True)]
    )
    claim = ExtractedClaim(
        claim_id="certification",
        category=ClaimCategory.OTHER,
        normalized_value=PUBLIC_FACT,
        source_text=f"Public status: {PUBLIC_FACT}",
        critical=False,
    )

    discovery = await PublicEvidenceService(provider).discover(
        claim, fact_type=PublicFactType.CERTIFICATION_STATUS
    )

    assert discovery.succeeded is True
    assert len(discovery.sources) == 1
    assert discovery.sources[0].canonical_url == "https://iafcertsearch.org/record"


@pytest.mark.asyncio
async def test_malformed_provider_response_fails_closed() -> None:
    provider = ScriptedPublicEvidenceProvider(
        [{"provider": "malformed", "candidates": [{"title": "missing everything"}]}]
    )
    claim = ExtractedClaim(
        claim_id="certification",
        category=ClaimCategory.OTHER,
        normalized_value=PUBLIC_FACT,
        source_text=f"Public status: {PUBLIC_FACT}",
        critical=False,
    )

    discovery = await PublicEvidenceService(provider).discover(
        claim, fact_type=PublicFactType.CERTIFICATION_STATUS
    )

    assert discovery.succeeded is False
    assert discovery.blocker_codes == ("PUBLIC_EVIDENCE_PROVIDER_INVALID",)


@pytest.mark.asyncio
async def test_verified_registry_can_pass_while_unknown_blog_remains_blocked(
    tmp_path: Path, phase2_draft
) -> None:
    initial = await initial_public_result(tmp_path, phase2_draft)
    certification = next(
        item for item in initial.verification.results if item.claim_id == "certification"
    )
    assert certification.status is VerificationStatus.UNSUPPORTED
    assert initial.baseline_decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert initial.profile_decision.outcome.value == "BLOCK"

    verified = await PublicEvidenceService(
        ScriptedPublicEvidenceProvider(
            [search_response(domain="iafcertsearch.org")]
        )
    ).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )
    unverified = await PublicEvidenceService(
        ScriptedPublicEvidenceProvider(
            [search_response(domain="unknown-cert-blog.example")]
        )
    ).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )

    assert verified.current_status is VerificationStatus.SUPPORTED
    assert verified.result.decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    verified_source = verified.result.evidence_documents[-1]
    assert verified_source.authority is EvidenceAuthority.VERIFIED_EXTERNAL
    assert verified_source.provenance.source_type is EvidenceSourceType.CERTIFICATION_REGISTRY
    assert unverified.current_status is VerificationStatus.SUPPORTED
    assert unverified.result.decision.outcome is PolicyOutcome.BLOCKED
    assert unverified.result.evidence_documents[-1].authority is (
        EvidenceAuthority.UNVERIFIED_EXTERNAL
    )
    assert "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES" in {
        blocker.code for blocker in unverified.result.profile_decision.blockers
    }


@pytest.mark.asyncio
async def test_public_provenance_enters_receipt_and_replay_never_searches(
    tmp_path: Path, phase2_draft
) -> None:
    initial = await initial_public_result(tmp_path, phase2_draft)
    provider = ScriptedPublicEvidenceProvider(
        [search_response(domain="iafcertsearch.org")]
    )
    enriched = await PublicEvidenceService(provider).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )
    receipt = issue_decision_receipt(result=enriched.result, created_at=FIXED_TIME)
    public_source = receipt.evidence.public_sources[0]
    calls_before = len(provider.requests)
    snapshot = capture_artifact_snapshot(
        pdf_path=enriched.result.pdf_path,
        evidence=enriched.result.evidence,
        policy_profile=enriched.result.selected_policy_profile,
        approval=None,
        esign=ReceiptESignSummary(status=ReceiptESignStatus.NOT_ATTEMPTED),
        expected_previous_receipt_sha256=None,
        action=build_sign_document_action(enriched.result),
        evidence_documents=enriched.result.evidence_documents,
    )

    replay = ReplayVerifier().verify(
        request=ReplayRequest(
            run_id=enriched.result.workflow.run_id,
            receipt_sha256=receipt.receipt_sha256,
        ),
        receipt=receipt,
        snapshot=snapshot,
    )
    changed_public_source = snapshot.public_evidence[0].model_copy(
        update={"domain": "changed-registry.example"}
    )
    provenance_drift = ReplayVerifier().verify(
        request=ReplayRequest(
            run_id=enriched.result.workflow.run_id,
            receipt_sha256=receipt.receipt_sha256,
        ),
        receipt=receipt,
        snapshot=snapshot.model_copy(
            update={"public_evidence": (changed_public_source,)}
        ),
    )

    assert public_source.provider == "scripted-search"
    assert public_source.domain == "iafcertsearch.org"
    assert public_source.authority is EvidenceAuthority.VERIFIED_EXTERNAL
    assert public_source.query == f'"{PUBLIC_FACT}"'
    assert replay.status is ReplayStatus.VERIFIED
    assert provenance_drift.status is ReplayStatus.DRIFT_DETECTED
    assert provenance_drift.blocker_codes == (
        "PUBLIC_EVIDENCE_PROVENANCE_MISMATCH",
    )
    assert len(provider.requests) == calls_before


@pytest.mark.asyncio
async def test_changed_public_evidence_changes_evidence_and_receipt_hashes(
    tmp_path: Path, phase2_draft
) -> None:
    initial = await initial_public_result(tmp_path, phase2_draft)
    first = await PublicEvidenceService(
        ScriptedPublicEvidenceProvider(
            [search_response(domain="iafcertsearch.org", snippet=PUBLIC_FACT)]
        )
    ).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )
    second = await PublicEvidenceService(
        ScriptedPublicEvidenceProvider(
            [
                search_response(
                    domain="iafcertsearch.org",
                    snippet=f"Registry match: {PUBLIC_FACT}",
                )
            ]
        )
    ).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )
    provenance_changed = await PublicEvidenceService(
        ScriptedPublicEvidenceProvider(
            [
                search_response(
                    domain="iafcertsearch.org",
                    snippet=PUBLIC_FACT,
                    retrieved_at=FIXED_TIME + timedelta(minutes=1),
                )
            ]
        )
    ).enrich_result(
        result=initial,
        claim_id="certification",
        fact_type=PublicFactType.CERTIFICATION_STATUS,
        semantic_engine=semantic_comparator(),
    )
    first_receipt = issue_decision_receipt(result=first.result, created_at=FIXED_TIME)
    second_receipt = issue_decision_receipt(result=second.result, created_at=FIXED_TIME)
    provenance_receipt = issue_decision_receipt(
        result=provenance_changed.result, created_at=FIXED_TIME
    )

    assert evidence_sha256(first.result.evidence) != evidence_sha256(second.result.evidence)
    assert first_receipt.receipt_sha256 != second_receipt.receipt_sha256
    assert evidence_sha256(first.result.evidence) != evidence_sha256(
        provenance_changed.result.evidence
    )
    assert first_receipt.receipt_sha256 != provenance_receipt.receipt_sha256


@pytest.mark.asyncio
async def test_serpapi_uses_fixed_backend_parameters_and_typed_organic_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/search"
        assert request.url.params["engine"] == "google"
        assert request.url.params["q"] == f'"{PUBLIC_FACT}"'
        assert request.url.params["api_key"] == "server-secret"
        assert request.url.params["num"] == "5"
        return httpx.Response(
            200,
            json={
                "search_metadata": {"id": "search-1", "status": "Success"},
                "organic_results": [
                    {
                        "position": 1,
                        "title": "Certification registry",
                        "link": "https://iafcertsearch.org/record",
                        "snippet": PUBLIC_FACT,
                    }
                ],
            },
        )

    provider = SerpApiPublicEvidenceProvider(
        api_key="server-secret",
        transport=httpx.MockTransport(handler),
    )
    claim = ExtractedClaim(
        claim_id="certification",
        category=ClaimCategory.OTHER,
        normalized_value=PUBLIC_FACT,
        source_text=f"Public status: {PUBLIC_FACT}",
        critical=False,
    )

    discovery = await PublicEvidenceService(provider).discover(
        claim, fact_type=PublicFactType.CERTIFICATION_STATUS
    )

    assert discovery.succeeded is True
    assert discovery.sources[0].authority is EvidenceAuthority.VERIFIED_EXTERNAL
    assert "server-secret" not in discovery.model_dump_json()
