from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from starlette.types import ASGIApp, Receive, Scope, Send

from claimgate.application import (
    ApprovalBoundaryError,
    ApprovalSendService,
    ProfileApprovalRecord,
)
from claimgate.domain import ApprovalRecord, WorkflowState
from claimgate.integrations.foxit_esign import ESignSendResult, Signer
from claimgate.policy_profiles import FINANCIAL_HIGH_RISK
from claimgate.web.app import create_app
from claimgate.web.auth import SESSION_COOKIE_NAME
from claimgate.web.service import Phase3DemoService

EXTRACTED_AGREEMENT = """ClaimGate Controlled Agreement
Party name: Acme Corporation
Contract amount: USD 12,500.00
Quantity: 250
Delivery date: 2026-09-30
Scope: Istanbul pilot deployment
Deliverable: 250 configured devices
Generated through Foxit PDF Services and subject to ClaimGate verification.
"""


class FakeFoxitPdfAdapter:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.has_public_fact = False

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        self.calls.append("generate")
        assert (
            "ClaimGate Controlled Agreement" in html
            or "ClaimGate Decision Receipt" in html
        )
        self.has_public_fact = "Example organization holds Certification X" in html
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"%PDF-1.4\nphase4-browser-safe-artifact")
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        self.calls.append("extract")
        assert pdf_path.read_bytes().startswith(b"%PDF-")
        extracted = EXTRACTED_AGREEMENT
        if self.has_public_fact:
            extracted += (
                "Public status: Example organization holds Certification X\n"
            )
        output_path.write_text(extracted)
        return extracted


class FakeESignSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[Path, Signer]] = []

    def send_pdf_for_signature(
        self, pdf_path: Path, signer: Signer
    ) -> ESignSendResult:
        self.calls.append((pdf_path, signer))
        if self.fail:
            raise RuntimeError("simulated Foxit failure")
        return ESignSendResult(folder_id="foxit-folder-9001")


class _SessionMiddleware:
    """Attach one local user session to product-flow tests.

    Authentication itself is exercised separately in ``tests/test_auth.py``;
    these tests focus on verification, policy, approval, receipt, and replay.
    """

    def __init__(self, app: ASGIApp, *, token: str) -> None:
        self.app = app
        self.cookie = f"{SESSION_COOKIE_NAME}={token}".encode("ascii")

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] == "http":
            scope = {**scope, "headers": [*scope["headers"], (b"cookie", self.cookie)]}
        await self.app(scope, receive, send)


def build_test_app(tmp_path: Path, *, esign_sender: FakeESignSender | None = None):
    adapters: list[FakeFoxitPdfAdapter] = []
    sender = esign_sender or FakeESignSender()

    def adapter_factory() -> FakeFoxitPdfAdapter:
        adapter = FakeFoxitPdfAdapter()
        adapters.append(adapter)
        return adapter

    app = create_app(
        demo_service=Phase3DemoService(adapter_factory),
        approval_service=ApprovalSendService(sender),
        signer_factory=lambda: Signer("signer@example.com", "Test", "Signer"),
        artifact_directory=tmp_path / "web-artifacts",
    )
    app.state.test_adapters = adapters
    app.state.test_esign_sender = sender
    user = app.state.users.create(
        full_name="Test Operator",
        email="web-tests@example.com",
        workspace_name="ClaimGate Tests",
        password="test-password",
    )
    token = app.state.sessions.create(user.user_id)
    app.add_middleware(_SessionMiddleware, token=token)
    return app


@pytest.mark.asyncio
async def test_landing_page_is_served_at_root(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        page = await client.get("/")

    assert page.status_code == 200
    assert "Control what AI agents are" in page.text
    assert "allowed to do" in page.text
    assert "Get started" in page.text
    assert "Sign in" in page.text
    assert 'href="/signup"' in page.text
    assert 'href="/login"' in page.text
    assert "default-src 'self'" in page.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_dashboard_and_static_assets_are_served(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # The unprefixed /workflows route is the backward-compatibility alias
        # for the app shell and is never gated by a session, so it is the
        # right target for an unauthenticated content check.
        page = await client.get("/workflows")
        script = await client.get("/static/app.js")
        stylesheet = await client.get("/static/app.css")
        logo = await client.get("/static/brand/claimgate-logo.png")
        favicon = await client.get("/static/brand/favicon-32.png")
        unknown_brand_asset = await client.get("/static/brand/not-allowed.png")

    assert page.status_code == 200
    assert "Workflow review" in page.text
    assert "Approve &amp; send for signature" in page.text
    assert "human-confirmation" in page.text
    assert "Agent cannot sign" in page.text
    assert "Relationship summary" in page.text
    assert "evidence-chain" in page.text
    assert "Attack validation suite" in page.text
    assert "Prove the boundary under pressure" in page.text
    assert "Audit History / Replay" in page.text
    assert "REPLAY VERIFICATION" in page.text
    assert script.status_code == 200
    assert "Verify document" in script.text
    assert "RUN ATTACK" in script.text
    assert "PDF_HASH_MISMATCH" not in script.text
    assert "runReplay" in script.text
    assert stylesheet.status_code == 200
    assert ".decision-banner.block" in stylesheet.text
    assert logo.status_code == 200
    assert logo.headers["content-type"] == "image/png"
    assert favicon.status_code == 200
    assert favicon.headers["content-type"] == "image/png"
    assert unknown_brand_asset.status_code == 404
    assert "default-src 'self'" in page.headers["content-security-policy"]


@pytest.mark.asyncio
async def test_attack_lab_catalog_and_controlled_runs_never_use_live_integrations(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        catalog = await client.get("/api/attack-lab")
        prompt_attack = await client.post(
            "/api/attack-lab/PROMPT_INJECTION_EVIDENCE/run"
        )
        duplicate_attack = await client.post("/api/attack-lab/DUPLICATE_SEND/run")
        unknown_attack = await client.post("/api/attack-lab/ARBITRARY_SCRIPT/run")

    assert catalog.status_code == 200
    catalog_payload = catalog.json()
    assert len(catalog_payload["scenarios"]) == 16
    assert len(catalog_payload["security_invariants"]) == 8
    assert all(item["passed"] for item in catalog_payload["security_invariants"])
    prompt_scenario = next(
        scenario
        for scenario in catalog_payload["scenarios"]
        if scenario["scenario_id"] == "PROMPT_INJECTION_EVIDENCE"
    )
    assert "Ignore previous instructions" in prompt_scenario["untrusted_evidence"]
    assert prompt_attack.status_code == 200
    assert prompt_attack.json()["workflow_state"] == "BLOCKED"
    assert prompt_attack.json()["simulated_esign_invocations"] == 0
    assert duplicate_attack.status_code == 200
    assert duplicate_attack.json()["simulated_esign_invocations"] == 1
    assert duplicate_attack.json()["observed_outcome"] == "SECOND_SEND_REJECTED"
    assert unknown_attack.status_code == 422
    assert app.state.test_esign_sender.calls == []
    assert app.state.test_adapters == []


@pytest.mark.asyncio
async def test_presets_expose_requests_and_non_secret_evidence(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/presets")

    assert response.status_code == 200
    presets = {item["id"]: item for item in response.json()["presets"]}
    assert set(presets) == {
        "safe",
        "conflicting",
        "evidence_graph",
        "public_certification",
        "unverified_public",
    }
    assert presets["safe"]["title"] == "Safe Agreement"
    assert "Create a delivery agreement" in presets["safe"]["plain_language_request"]
    assert {source["kind"] for source in presets["safe"]["evidence_sources"]} == {
        "plain_text",
        "pdf_derived_text",
    }
    conflicting_text = "\n".join(
        source["content"] for source in presets["conflicting"]["evidence_sources"]
    )
    assert "Contract amount: USD 15,000.00" in conflicting_text
    graph_sources = presets["evidence_graph"]["evidence_sources"]
    assert len(graph_sources) == 4
    assert {source["authority"] for source in graph_sources} == {
        "AUTHORITATIVE_INTERNAL",
        "VERIFIED_EXTERNAL",
        "UNVERIFIED_EXTERNAL",
    }
    assert "client_secret" not in response.text.lower()
    assert "SERPAPI_API_KEY" not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.asyncio
async def test_builtin_policy_profiles_are_exposed_without_configuration_controls(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/policy-profiles")

    assert response.status_code == 200
    profiles = {item["id"]: item for item in response.json()["profiles"]}
    assert set(profiles) == {
        "standard-contract-v1",
        "financial-high-risk-v1",
        "procurement-strict-v1",
        "public-evidence-strict-v1",
    }
    assert "two money sources" in profiles["financial-high-risk-v1"][
        "description"
    ].lower()
    assert all(len(profile["profile_hash"]) == 64 for profile in profiles.values())
    assert "categories" not in response.text


@pytest.mark.asyncio
async def test_public_certification_search_reevaluates_policy_and_chains_receipt(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            "/api/runs",
            json={
                "preset": "public_certification",
                "policy_profile": "public-evidence-strict-v1",
            },
        )
        initial = await client.get(started.json()["status_url"])
        initial_result = initial.json()["result"]
        certification = next(
            claim
            for claim in initial_result["claims"]
            if claim["claim_id"] == "certification"
        )
        searched = await client.post(certification["public_search"]["url"])
        duplicate = await client.post(certification["public_search"]["url"])
        enriched_receipt_hash = searched.json()["receipt"]["receipt_sha256"]
        receipt_verification = await client.post(
            searched.json()["receipt"]["verify_url"]
        )
        replayed = await client.post(
            f"/api/runs/{started.json()['run_id']}/replay",
            json={
                "receipt_sha256": enriched_receipt_hash,
                "preset": "CLEAN_REPLAY",
            },
        )

    assert initial_result["decision"] == "SIGNING_BLOCKED"
    assert certification["status"] == "UNSUPPORTED"
    assert certification["public_search"]["eligible"] is True
    updated = searched.json()
    assert updated["public_evidence_update"]["previous_status"] == "UNSUPPORTED"
    assert updated["public_evidence_update"]["current_status"] == "SUPPORTED"
    assert updated["public_evidence_update"]["reevaluated"] is True
    assert updated["decision"] == "READY_FOR_HUMAN_APPROVAL"
    assert updated["policy_evaluation"] == {
        "baseline": "PASS",
        "profile": "PASS",
        "final": "READY",
        "profile_blockers": [],
    }
    public_source = next(
        source for source in updated["evidence_graph"]["evidence"] if source["public"]
    )
    assert public_source["authority"] == "VERIFIED_EXTERNAL"
    assert public_source["provenance"]["source_type"] == "CERTIFICATION_REGISTRY"
    assert public_source["provenance"]["provider"] == "scripted-public-search"
    assert public_source["provenance"]["domain"] == "iafcertsearch.org"
    assert len(updated["audit_history"]["receipts"]) == 2
    assert updated["audit_history"]["original_final_decision"] == "BLOCKED"
    assert updated["audit_history"]["timeline"][-1]["kind"] == (
        "PUBLIC_EVIDENCE_REEVALUATION"
    )
    assert updated["receipt"]["structured"]["evidence"]["public_sources"][0][
        "domain"
    ] == "iafcertsearch.org"
    assert duplicate.status_code == 409
    assert receipt_verification.json()["status"] == "VERIFIED"
    assert replayed.json()["status"] == "VERIFIED"
    replay_checks = {
        check["check_id"]: check for check in replayed.json()["checks"]
    }
    assert replay_checks["public_evidence_provenance"]["status"] == "PASS"
    assert app.state.test_esign_sender.calls == []
    stored_run = app.state.run_registry.get(started.json()["run_id"])
    assert stored_run.result.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert stored_run.result.workflow.approval is None
    assert stored_run.profile_approval is None
    assert stored_run.send_attempted is False
    assert "SERPAPI_API_KEY" not in searched.text


@pytest.mark.asyncio
async def test_unverified_public_source_remains_blocked_by_strict_profile(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post(
            "/api/runs",
            json={
                "preset": "unverified_public",
                "policy_profile": "public-evidence-strict-v1",
            },
        )
        initial = await client.get(started.json()["status_url"])
        certification = next(
            claim
            for claim in initial.json()["result"]["claims"]
            if claim["claim_id"] == "certification"
        )
        searched = await client.post(certification["public_search"]["url"])

    result = searched.json()
    assert result["public_evidence_update"]["current_status"] == "SUPPORTED"
    assert result["decision"] == "SIGNING_BLOCKED"
    public_source = next(
        source for source in result["evidence_graph"]["evidence"] if source["public"]
    )
    assert public_source["authority"] == "UNVERIFIED_EXTERNAL"
    assert public_source["provenance"]["source_type"] == "UNKNOWN_THIRD_PARTY"
    assert "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES" in {
        blocker["code"] for blocker in result["policy_evaluation"]["profile_blockers"]
    }
    assert result["approval_available"] is False
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_safe_run_reaches_human_approval_placeholder(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run = await client.get(started.json()["status_url"])
        pdf = await client.get(run.json()["result"]["pdf_url"])
        unconfirmed_send = await client.post(
            f"/api/runs/{started.json()['run_id']}/approve-and-send",
            json={"confirmed": False},
        )

    assert started.status_code == 202
    payload = run.json()
    assert payload["status"] == "complete"
    assert [step["label"] for step in payload["progress"]] == [
        "Generating document",
        "Extracting final PDF",
        "Extracting material claims",
        "Checking evidence",
        "Applying deterministic policy",
    ]
    assert all(step["status"] == "complete" for step in payload["progress"])
    assert payload["result"]["decision"] == "READY_FOR_HUMAN_APPROVAL"
    assert payload["result"]["approval_available"] is True
    assert payload["result"]["audit"]["workflow_state"] == "READY_FOR_APPROVAL"
    assert payload["result"]["policy_evaluation"] == {
        "baseline": "PASS",
        "profile": "PASS",
        "final": "READY",
        "profile_blockers": [],
    }
    assert payload["result"]["audit"]["selected_profile"] == (
        "standard-contract-v1"
    )
    assert len(payload["result"]["audit"]["policy_profile_hash"]) == 64
    assert payload["result"]["receipt"]["final_decision"] == "PASS"
    assert len(payload["result"]["receipt"]["receipt_sha256"]) == 64
    assert payload["result"]["receipt"]["structured"]["approval"][
        "occurred"
    ] is False
    assert len(payload["result"]["claims"]) == 6
    assert all(claim["status"] == "SUPPORTED" for claim in payload["result"]["claims"])
    assert all(claim["evidence_quote"] for claim in payload["result"]["claims"])
    assert payload["result"]["evidence_graph"]["summary"] == {
        "material_claims": 6,
        "evidence_sources": 2,
        "support_count": 6,
        "conflict_count": 0,
        "uncertain_count": 0,
        "authoritative_support_count": 6,
        "authoritative_conflict_count": 0,
    }
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-")
    assert unconfirmed_send.status_code == 400
    assert app.state.test_esign_sender.calls == []
    assert app.state.test_adapters[0].calls == ["generate", "extract"]


@pytest.mark.asyncio
async def test_receipt_json_verification_pdf_and_chain_endpoints(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first_started = await client.post("/api/runs", json={"preset": "safe"})
        first = await client.get(first_started.json()["status_url"])
        first_receipt = first.json()["result"]["receipt"]
        verification = await client.post(first_receipt["verify_url"])
        canonical_json = await client.get(first_receipt["canonical_json_url"])
        generated_pdf = await client.post(first_receipt["generate_pdf_url"])
        receipt_pdf = await client.get(generated_pdf.json()["pdf_url"])

        second_started = await client.post(
            "/api/runs", json={"preset": "conflicting"}
        )
        second = await client.get(second_started.json()["status_url"])

    assert verification.status_code == 200
    assert verification.json()["status"] == "VERIFIED"
    assert verification.json()["blocker_codes"] == []
    assert canonical_json.status_code == 200
    assert canonical_json.json()["receipt_sha256"] == first_receipt["receipt_sha256"]
    assert "attachment" in canonical_json.headers["content-disposition"]
    assert receipt_pdf.status_code == 200
    assert receipt_pdf.headers["content-type"] == "application/pdf"
    assert receipt_pdf.content.startswith(b"%PDF-")
    second_receipt = second.json()["result"]["receipt"]
    assert second_receipt["sequence"] == first_receipt["sequence"] + 1
    assert second_receipt["previous_receipt_sha256"] == first_receipt[
        "receipt_sha256"
    ]
    assert second_receipt["final_decision"] == "BLOCKED"
    assert second_receipt["structured"]["blocker_codes"]


@pytest.mark.asyncio
async def test_read_only_replay_endpoint_reports_individual_checks_and_drift(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        completed = await client.get(started.json()["status_url"])
        result = completed.json()["result"]
        history = result["audit_history"]
        receipt_hash = history["receipts"][0]["receipt_sha256"]
        calls_before = list(app.state.test_adapters[0].calls)

        clean = await client.post(
            f"/api/runs/{run_id}/replay",
            json={"receipt_sha256": receipt_hash, "preset": "CLEAN_REPLAY"},
        )
        pdf_drift = await client.post(
            f"/api/runs/{run_id}/replay",
            json={"receipt_sha256": receipt_hash, "preset": "PDF_DRIFT"},
        )
        policy_drift = await client.post(
            f"/api/runs/{run_id}/replay",
            json={"receipt_sha256": receipt_hash, "preset": "POLICY_DRIFT"},
        )
        broken_chain = await client.post(
            f"/api/runs/{run_id}/replay",
            json={"receipt_sha256": receipt_hash, "preset": "BROKEN_CHAIN"},
        )
        unknown_receipt = await client.post(
            f"/api/runs/{run_id}/replay",
            json={"receipt_sha256": "f" * 64, "preset": "CLEAN_REPLAY"},
        )
        unsafe_input = await client.post(
            f"/api/runs/{run_id}/replay",
            json={
                "receipt_sha256": receipt_hash,
                "preset": "CLEAN_REPLAY",
                "pdf_path": "/tmp/browser-controlled.pdf",
            },
        )

    assert history["original_final_decision"] == "PASS"
    assert history["current_workflow_state"] == "READY_FOR_APPROVAL"
    assert history["policy_profile_id"] == "standard-contract-v1"
    assert history["pdf_sha256"] == result["audit"]["pdf_sha256"]
    assert history["evidence_sha256"] == result["audit"]["evidence_sha256"]
    assert history["replay_presets"] == [
        "CLEAN_REPLAY",
        "PDF_DRIFT",
        "EVIDENCE_DRIFT",
        "POLICY_DRIFT",
        "BROKEN_CHAIN",
        "ACTION_PARAMETER_DRIFT",
    ]
    assert [event["kind"] for event in history["timeline"]] == [
        "RUN_CREATED",
        "VERIFICATION_RECEIPT",
    ]
    assert clean.status_code == 200
    assert clean.json()["status"] == "VERIFIED"
    assert all(check["status"] == "PASS" for check in clean.json()["checks"])
    assert pdf_drift.json()["status"] == "DRIFT_DETECTED"
    assert pdf_drift.json()["blocker_codes"] == ["PDF_HASH_MISMATCH"]
    assert policy_drift.json()["status"] == "DRIFT_DETECTED"
    assert policy_drift.json()["blocker_codes"] == [
        "POLICY_PROFILE_HASH_MISMATCH"
    ]
    assert broken_chain.json()["status"] == "CHAIN_BROKEN"
    assert unknown_receipt.status_code == 404
    assert unsafe_input.status_code == 422
    assert app.state.test_adapters[0].calls == calls_before
    assert app.state.test_esign_sender.calls == []
    stored = app.state.run_registry.get(run_id)
    assert stored.result.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert len(stored.receipt_history) == 1
    assert stored.profile_approval is None


@pytest.mark.asyncio
async def test_conflicting_run_surfaces_exact_money_blocker(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "conflicting"})
        run = await client.get(started.json()["status_url"])

    payload = run.json()["result"]
    money = next(claim for claim in payload["claims"] if claim["claim_id"] == "money")
    assert payload["decision"] == "SIGNING_BLOCKED"
    assert payload["approval_available"] is False
    assert payload["audit"]["workflow_state"] == "BLOCKED"
    assert money["status"] == "CONFLICTING"
    assert money["evidence_quote"] == "Contract amount: USD 15,000.00"
    assert payload["blockers"][0]["code"] == "CRITICAL_CLAIM_CONFLICTING"
    assert payload["blockers"][0]["explanation"] == (
        "Contract amount is USD 12,500.00 in the document but "
        "USD 15,000.00 in the authoritative quote."
    )


@pytest.mark.asyncio
async def test_mixed_graph_run_exposes_entire_money_evidence_chain(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "evidence_graph"})
        run = await client.get(started.json()["status_url"])

    payload = run.json()["result"]
    graph = payload["evidence_graph"]
    money_edges = [edge for edge in graph["edges"] if edge["claim_id"] == "money"]
    assert payload["decision"] == "SIGNING_BLOCKED"
    assert payload["approval_available"] is False
    assert graph["summary"]["support_count"] == 7
    assert graph["summary"]["conflict_count"] == 1
    assert [edge["relationship"] for edge in money_edges] == [
        "SUPPORTS",
        "SUPPORTS",
        "CONFLICTS",
    ]
    assert money_edges[-1]["quotation"] == (
        "Requested contract amount: USD 15,000.00"
    )
    conflicting_source = next(
        source
        for source in graph["evidence"]
        if source["source_id"] == money_edges[-1]["evidence_id"]
    )
    assert conflicting_source["authority"] == "UNVERIFIED_EXTERNAL"
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_same_safe_demo_blocks_under_financial_high_risk_profile(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        standard_started = await client.post(
            "/api/runs",
            json={"preset": "safe", "policy_profile": "standard-contract-v1"},
        )
        financial_started = await client.post(
            "/api/runs",
            json={"preset": "safe", "policy_profile": "financial-high-risk-v1"},
        )
        standard = await client.get(standard_started.json()["status_url"])
        financial = await client.get(financial_started.json()["status_url"])

    standard_result = standard.json()["result"]
    financial_result = financial.json()["result"]
    assert standard_result["policy_evaluation"] == {
        "baseline": "PASS",
        "profile": "PASS",
        "final": "READY",
        "profile_blockers": [],
    }
    assert financial_result["policy_evaluation"]["baseline"] == "PASS"
    assert financial_result["policy_evaluation"]["profile"] == "BLOCK"
    assert financial_result["policy_evaluation"]["final"] == "BLOCKED"
    assert financial_result["decision"] == "SIGNING_BLOCKED"
    assert financial_result["policy_evaluation"]["profile_blockers"][0][
        "code"
    ] == "PROFILE_INSUFFICIENT_SUPPORTING_SOURCES"
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_browser_cannot_supply_document_fields_or_fetch_unknown_pdf(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        arbitrary_document = await client.post(
            "/api/runs",
            json={"preset": "safe", "contract_amount": "1.00"},
        )
        unknown_pdf = await client.get("/api/runs/not-a-run/pdf")

    assert arbitrary_document.status_code == 422
    assert unknown_pdf.status_code == 404
    assert app.state.test_adapters == []


@pytest.mark.asyncio
async def test_ready_run_requires_confirmation_then_sends_once(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        sent = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )
        duplicate = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )
        refreshed = await client.get(f"/api/runs/{run_id}")
        sent_receipt_hash = refreshed.json()["result"]["audit_history"][
            "receipts"
        ][-1]["receipt_sha256"]
        replayed_send = await client.post(
            f"/api/runs/{run_id}/replay",
            json={
                "receipt_sha256": sent_receipt_hash,
                "preset": "CLEAN_REPLAY",
            },
        )

    assert sent.status_code == 200
    assert sent.json() == {
        "attempted": True,
        "state": "SENT",
        "folder_id": "foxit-folder-9001",
        "error": None,
    }
    assert duplicate.status_code == 409
    assert refreshed.json()["result"]["audit"]["workflow_state"] == "SENT"
    assert refreshed.json()["result"]["approval_available"] is False
    send_history = refreshed.json()["result"]["audit_history"]
    assert [event["kind"] for event in send_history["timeline"]] == [
        "RUN_CREATED",
        "VERIFICATION_RECEIPT",
        "HUMAN_APPROVAL",
        "ESIGN_ATTEMPT",
        "SEND_RECEIPT",
    ]
    assert send_history["timeline"][-1]["state"] == "SENT"
    assert len(send_history["receipts"]) == 2
    assert replayed_send.json()["status"] == "VERIFIED"
    checks = {check["check_id"]: check for check in replayed_send.json()["checks"]}
    assert checks["approval_binding"]["status"] == "PASS"
    assert checks["esign_state"]["status"] == "PASS"
    assert checks["previous_receipt"]["status"] == "PASS"
    stored_run = app.state.run_registry.get(run_id)
    assert stored_run.result.workflow.approval.binding == stored_run.result.decision.binding
    assert isinstance(stored_run.profile_approval, ProfileApprovalRecord)
    assert stored_run.profile_approval.binding == (
        *stored_run.result.decision.binding,
        stored_run.result.selected_policy_profile.id,
        stored_run.result.selected_policy_profile.profile_hash,
    )
    assert len(stored_run.receipt_history) == 2
    sent_receipt = stored_run.receipt_history[-1].receipt
    assert sent_receipt.workflow_state is WorkflowState.SENT
    assert sent_receipt.approval.occurred is True
    assert sent_receipt.esign.status.value == "SENT"
    assert sent_receipt.esign.foxit_identifier == "foxit-folder-9001"
    assert sent_receipt.previous_receipt_sha256 == stored_run.receipt_history[
        0
    ].receipt.receipt_sha256
    assert len(app.state.test_esign_sender.calls) == 1


@pytest.mark.asyncio
async def test_changed_policy_profile_invalidates_approval(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        run = app.state.run_registry.get(run_id)
        run.result = replace(
            run.result,
            selected_policy_profile=FINANCIAL_HIGH_RISK,
        )
        response = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Policy profile changed after verification"
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_changed_profile_contents_with_same_id_invalidates_approval(
    tmp_path: Path,
) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        run = app.state.run_registry.get(run_id)
        changed_profile = run.result.selected_policy_profile.model_copy(
            update={"description": "Changed after verification."}
        )
        run.result = replace(
            run.result,
            selected_policy_profile=changed_profile,
        )
        response = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Policy profile contents changed after verification"
    )
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_blocked_run_cannot_send(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "conflicting"})
        response = await client.post(
            f"/api/runs/{started.json()['run_id']}/approve-and-send",
            json={"confirmed": True},
        )

    assert response.status_code == 409
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_changed_pdf_cannot_send(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        run = app.state.run_registry.get(run_id)
        with run.result.pdf_path.open("ab") as pdf_file:
            pdf_file.write(b"\ntampered-after-policy")
        response = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "PDF changed after verification"
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_changed_evidence_cannot_send(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        run = app.state.run_registry.get(run_id)
        changed_source = replace(
            run.result.evidence[0],
            content=run.result.evidence[0].content + "\nChanged after verification",
        )
        run.result = replace(
            run.result,
            evidence=(changed_source, *run.result.evidence[1:]),
        )
        response = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Evidence changed after verification"
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_stale_approval_cannot_send(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
    run = app.state.run_registry.get(started.json()["run_id"])
    stale = ApprovalRecord(
        approved_by="Test human",
        approved_at=datetime.now(timezone.utc),
        pdf_sha256="0" * 64,
        evidence_sha256=run.result.decision.evidence_sha256,
        policy_version=run.result.decision.policy_version,
    )

    with pytest.raises(ApprovalBoundaryError, match="binding is stale"):
        app.state.approval_service.approve_and_send(
            result=run.result,
            signer=Signer("signer@example.com", "Test", "Signer"),
            approved_by="Test human",
            confirmed=True,
            approval=stale,
        )

    assert run.result.workflow.state is WorkflowState.READY_FOR_APPROVAL
    assert app.state.test_esign_sender.calls == []


@pytest.mark.asyncio
async def test_esign_failure_is_terminal_and_not_retried(tmp_path: Path) -> None:
    sender = FakeESignSender(fail=True)
    app = build_test_app(tmp_path, esign_sender=sender)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        failed = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )
        duplicate = await client.post(
            f"/api/runs/{run_id}/approve-and-send",
            json={"confirmed": True},
        )

    assert failed.status_code == 200
    assert failed.json()["state"] == "SEND_FAILED"
    assert failed.json()["folder_id"] is None
    assert "not retried" in failed.json()["error"]
    assert duplicate.status_code == 409
    assert len(sender.calls) == 1
    run = app.state.run_registry.get(run_id)
    assert len(run.receipt_history) == 2
    assert run.receipt_history[-1].receipt.esign.status.value == "SEND_FAILED"


def test_semantic_provider_package_has_no_esign_capability() -> None:
    semantic_directory = Path(__file__).parents[1] / "src" / "claimgate" / "semantic"
    semantic_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in semantic_directory.glob("*.py")
    )

    assert "foxit_esign" not in semantic_source
    assert "FoxitESignClient" not in semantic_source
    assert "send_pdf_for_signature" not in semantic_source


@pytest.mark.asyncio
async def test_actions_catalog_is_read_only_and_matches_registry(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        catalog = await client.get("/api/actions/catalog")

    assert catalog.status_code == 200
    capabilities = {item["action_type"]: item for item in catalog.json()["capabilities"]}
    assert set(capabilities) == {
        "SIGN_DOCUMENT",
        "SEND_EMAIL",
        "DEPLOY_SOFTWARE",
        "EXECUTE_PURCHASE",
        "EXECUTE_PAYMENT",
        "DATABASE_WRITE",
    }
    assert capabilities["SIGN_DOCUMENT"]["live_execution"] is True
    assert capabilities["SIGN_DOCUMENT"]["adapter"] == "FOXIT_ESIGN"
    for action_type, capability in capabilities.items():
        if action_type != "SIGN_DOCUMENT":
            assert capability["live_execution"] is False
            assert capability["adapter"] == "SIMULATED"


@pytest.mark.asyncio
async def test_sign_document_run_receipt_includes_action_metadata(tmp_path: Path) -> None:
    app = build_test_app(tmp_path)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        started = await client.post("/api/runs", json={"preset": "safe"})
        run_id = started.json()["run_id"]
        completed = await client.get(started.json()["status_url"])
        sent = await client.post(
            f"/api/runs/{run_id}/approve-and-send", json={"confirmed": True}
        )

    result = completed.json()["result"]
    assert result["action"]["action_type"] == "SIGN_DOCUMENT"
    assert result["action"]["risk"] == "IRREVERSIBLE"
    assert result["action"]["execution_capability"]["adapter"] == "FOXIT_ESIGN"
    assert result["action"]["execution_capability"]["live_execution"] is True
    assert sent.status_code == 200
    stored_run = app.state.run_registry.get(run_id)
    receipt = stored_run.receipt_history[-1].receipt
    assert receipt.action_type.value == "SIGN_DOCUMENT"
    assert receipt.action_risk.value == "IRREVERSIBLE"
    assert len(receipt.action_sha256) == 64
    assert receipt.execution_capability.adapter == "FOXIT_ESIGN"
