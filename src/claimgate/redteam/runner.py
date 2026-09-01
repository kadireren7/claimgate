"""Controlled attacks that exercise existing ClaimGate safety boundaries."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from claimgate.actions import (
    ActionApprovalRecord,
    ActionExecutionError,
    ActionType,
    FoxitSignDocumentExecutor,
    SimulatedActionExecutor,
    create_proposed_action,
    get_capability,
    get_executor,
    is_approval_valid,
)
from claimgate.application import (
    ApprovalBoundaryError,
    ApprovalSendService,
    DraftDocument,
    Phase3Preset,
    Phase3Result,
    Phase3Workflow,
    ProfileApprovalRecord,
    build_phase3_preset,
    build_sign_document_action,
)
from claimgate.audit import (
    ReceiptESignStatus,
    ReceiptESignSummary,
    ReceiptVerificationContext,
    issue_decision_receipt,
    verify_receipt,
)
from claimgate.domain import (
    ApprovalRecord,
    PolicyBlocker,
    PolicyDecision,
    PolicyOutcome,
    WorkflowState,
)
from claimgate.evidence_graph import EvidenceAuthority, EvidenceGraph
from claimgate.evidence_graph.builder import build_evidence_graph
from claimgate.integrations.foxit_esign import ESignSendResult, Signer
from claimgate.policy_profiles import (
    FINANCIAL_HIGH_RISK,
    PUBLIC_EVIDENCE_STRICT,
    STANDARD_CONTRACT,
    PolicyEvaluationContext,
    PolicyProfileEvaluator,
)
from claimgate.public_evidence import (
    PUBLIC_EVIDENCE_SNIPPET_MARKER,
    PublicEvidenceService,
    PublicFactType,
    ScriptedPublicEvidenceProvider,
)
from claimgate.redteam.models import (
    AttackOutcome,
    AttackResult,
    AttackScenario,
    AttackScenarioId,
    SecurityAssertion,
)
from claimgate.redteam.scenarios import (
    ATTACK_SCENARIOS,
    PROMPT_INJECTION_TEXT,
    SCENARIOS_BY_ID,
)
from claimgate.replay import (
    ReplayPreset,
    ReplayRequest,
    ReplayStatus,
    ReplayVerifier,
    apply_replay_preset,
    capture_artifact_snapshot,
)
from claimgate.semantic import (
    EvidenceDocument,
    ScriptedSemanticProvider,
    SemanticEngine,
    SemanticOperation,
    SemanticVerificationStatus,
    StructuredRequest,
)
from claimgate.semantic.models import EvidenceComparison

EXTRACTED_AGREEMENT = """ClaimGate Controlled Agreement
Party name: Acme Corporation
Contract amount: USD 12,500.00
Quantity: 250
Delivery date: 2026-09-30
Scope: Istanbul pilot deployment
Deliverable: 250 configured devices
Generated through Foxit PDF Services and subject to ClaimGate verification.
"""
class _ControlledPdfAdapter:
    """Local deterministic artifact adapter; Attack Lab never calls Foxit."""

    def __init__(
        self, artifact_token: str, *, extracted_text: str = EXTRACTED_AGREEMENT
    ) -> None:
        self._artifact_token = artifact_token
        self._extracted_text = extracted_text

    async def generate_pdf_from_html(self, html: str, output_path: Path) -> Path:
        if "ClaimGate Controlled Agreement" not in html:
            raise ValueError("Controlled agreement template was not rendered")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(
            b"%PDF-1.4\nclaimgate-attack-lab\n" + self._artifact_token.encode("ascii")
        )
        return output_path

    async def extract_text_from_pdf(self, pdf_path: Path, output_path: Path) -> str:
        if not pdf_path.read_bytes().startswith(b"%PDF-"):
            raise ValueError("Controlled artifact is not a PDF")
        output_path.write_text(self._extracted_text, encoding="utf-8")
        return self._extracted_text


class _MutatingSemanticProvider:
    def __init__(
        self,
        delegate: ScriptedSemanticProvider,
        mutation: Callable[[dict[str, object]], None],
    ) -> None:
        self._delegate = delegate
        self._mutation = mutation

    async def complete_structured(self, request: StructuredRequest) -> object:
        response = await self._delegate.complete_structured(request)
        if request.operation is SemanticOperation.VERIFY_EVIDENCE:
            if not isinstance(response, dict):
                raise TypeError("Controlled semantic response must be a dictionary")
            self._mutation(response)
        return response


class _RecordingESignSender:
    """Records boundary calls without network, credentials, email, or Foxit access."""

    def __init__(self) -> None:
        self.calls = 0

    def send_pdf_for_signature(self, pdf_path: Path, signer: Signer) -> ESignSendResult:
        self.calls += 1
        return ESignSendResult(folder_id="attack-lab-local-simulation")


class AttackRunner:
    """Run only fixed scenarios through existing ClaimGate components."""

    def __init__(self, artifact_directory: Path) -> None:
        self._artifact_directory = artifact_directory.resolve()

    @property
    def scenarios(self) -> tuple[AttackScenario, ...]:
        return ATTACK_SCENARIOS

    async def run(self, scenario_id: AttackScenarioId) -> AttackResult:
        runners = {
            AttackScenarioId.PROMPT_INJECTION_EVIDENCE: self._prompt_injection,
            AttackScenarioId.INVENTED_QUOTATION: self._invented_quotation,
            AttackScenarioId.UNKNOWN_EVIDENCE_REFERENCE: self._unknown_reference,
            AttackScenarioId.AUTHORITATIVE_CONFLICT: self._authoritative_conflict,
            AttackScenarioId.PDF_TAMPER_AFTER_VERIFICATION: self._pdf_tamper,
            AttackScenarioId.EVIDENCE_TAMPER_AFTER_VERIFICATION: self._evidence_tamper,
            AttackScenarioId.POLICY_TAMPER_AFTER_VERIFICATION: self._policy_tamper,
            AttackScenarioId.REPLAYED_APPROVAL: self._replayed_approval,
            AttackScenarioId.DUPLICATE_SEND: self._duplicate_send,
            AttackScenarioId.RECEIPT_TAMPER: self._receipt_tamper,
            AttackScenarioId.HISTORICAL_ARTIFACT_DRIFT: (
                self._historical_artifact_drift
            ),
            AttackScenarioId.SEARCH_RESULT_POISONING: self._search_result_poisoning,
            AttackScenarioId.UNVERIFIED_EXTERNAL_ONLY: self._unverified_external_only,
            AttackScenarioId.ACTION_PARAMETER_TAMPER: self._action_parameter_tamper,
            AttackScenarioId.ACTION_TYPE_SWAP: self._action_type_swap,
            AttackScenarioId.EXECUTION_CAPABILITY_ESCALATION: (
                self._execution_capability_escalation
            ),
        }
        return await runners[scenario_id]()

    def security_invariants(self) -> tuple[SecurityAssertion, ...]:
        package_directory = Path(__file__).parents[1]
        semantic_source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (package_directory / "semantic").glob("*.py")
        )
        frontend_source = "\n".join(
            path.read_text(encoding="utf-8")
            for directory in (
                package_directory / "web" / "static",
                package_directory / "web" / "templates",
            )
            for path in directory.glob("*")
            if path.is_file()
        )
        provider = ScriptedSemanticProvider([])
        profile_isolation = "policy_profiles" not in semantic_source
        no_esign = all(
            marker not in semantic_source
            for marker in ("FoxitESignClient", "foxit_esign", "send_pdf_for_signature")
        ) and not hasattr(provider, "send_pdf_for_signature")
        no_workflow = all(
            not hasattr(provider, operation)
            for operation in ("approve", "start_sending", "mark_sent")
        )
        browser_has_no_credentials = all(
            marker not in frontend_source
            for marker in ("FOXIT_", "client_secret", "api_key", "Authorization: Bearer")
        )
        registry_source = (package_directory / "actions" / "registry.py").read_text(
            encoding="utf-8"
        )
        registry_is_static = "def register" not in registry_source
        semantic_has_no_action_import = "claimgate.actions" not in semantic_source

        baseline_approval = ApprovalRecord(
            approved_by="Attack Lab",
            approved_at=datetime.now(timezone.utc),
            pdf_sha256="a" * 64,
            evidence_sha256="b" * 64,
            policy_version="claimgate-policy-v1",
        )
        profile_approval = ProfileApprovalRecord(
            baseline_approval=baseline_approval,
            policy_profile_id=STANDARD_CONTRACT.id,
            policy_profile_hash=STANDARD_CONTRACT.profile_hash,
        )
        approval_bound = len(profile_approval.binding) == 5
        blocked_baseline = PolicyDecision(
            outcome=PolicyOutcome.BLOCKED,
            pdf_sha256="a" * 64,
            evidence_sha256="b" * 64,
            policy_version="claimgate-policy-v1",
            blockers=(
                PolicyBlocker(
                    code="ATTACK_LAB_BASELINE_BLOCK",
                    message="Controlled baseline rejection",
                ),
            ),
        )
        profile_evaluation = PolicyProfileEvaluator().evaluate(
            PolicyEvaluationContext(
                baseline_decision=blocked_baseline,
                selected_profile=STANDARD_CONTRACT,
                evidence_graph=EvidenceGraph(claims=(), evidence=(), edges=()),
            )
        )
        profile_preserves_baseline = (
            profile_evaluation.final_decision == blocked_baseline
        )

        return (
            SecurityAssertion(
                assertion_id="SEMANTIC_NO_ESIGN",
                statement="Semantic provider has no eSign capability.",
                passed=no_esign,
                observed_evidence=(
                    "Semantic package and provider expose no eSign client or send method."
                ),
            ),
            SecurityAssertion(
                assertion_id="EVIDENCE_NO_POLICY_MUTATION",
                statement="Evidence cannot mutate policy configuration.",
                passed=profile_isolation,
                observed_evidence=(
                    "Semantic package has no policy-profile import or configuration handle."
                ),
            ),
            SecurityAssertion(
                assertion_id="EVIDENCE_NO_WORKFLOW_MUTATION",
                statement="Evidence cannot mutate workflow state.",
                passed=no_workflow,
                observed_evidence="Provider exposes no approval or workflow-transition methods.",
            ),
            SecurityAssertion(
                assertion_id="BROWSER_NO_FOXIT_CREDENTIALS",
                statement="Browser has no Foxit credentials.",
                passed=browser_has_no_credentials,
                observed_evidence=(
                    "Served HTML and JavaScript contain no Foxit secret or authorization fields."
                ),
            ),
            SecurityAssertion(
                assertion_id="APPROVAL_ARTIFACT_BOUND",
                statement="Approval is artifact- and profile-bound.",
                passed=approval_bound,
                observed_evidence=(
                    "Approval binding contains PDF, evidence, baseline, profile ID, and "
                    "profile hash."
                ),
            ),
            SecurityAssertion(
                assertion_id="PROFILE_CANNOT_WEAKEN_BASELINE",
                statement="Profiles may tighten baseline policy but never weaken it.",
                passed=profile_preserves_baseline,
                observed_evidence=(
                    "A controlled blocked baseline remained the final decision after profile "
                    "evaluation."
                ),
            ),
            SecurityAssertion(
                assertion_id="ACTION_REGISTRY_IS_STATIC",
                statement="The action capability registry is static and code-only.",
                passed=registry_is_static,
                observed_evidence=(
                    "actions/registry.py defines no function to register or mutate a "
                    "capability entry."
                ),
            ),
            SecurityAssertion(
                assertion_id="SEMANTIC_HAS_NO_ACTION_IMPORT",
                statement="The semantic provider cannot assign or escalate execution capability.",
                passed=semantic_has_no_action_import,
                observed_evidence=(
                    "The semantic package has no import of claimgate.actions."
                ),
            ),
        )

    async def _prompt_injection(self) -> AttackResult:
        bundle = build_phase3_preset(self._draft(), Phase3Preset.PASS)
        evidence_documents = list(bundle.evidence_documents)
        first = evidence_documents[0]
        evidence_documents[0] = replace(
            first,
            source=replace(
                first.source,
                content=f"{first.source.content}\n\n{PROMPT_INJECTION_TEXT}",
            ),
        )

        def inject_policy_fields(response: dict[str, object]) -> None:
            response["workflow_state"] = "SENT"
            response["approve_and_send"] = True

        result = await self._workflow(
            AttackScenarioId.PROMPT_INJECTION_EVIDENCE,
            evidence_documents=tuple(evidence_documents),
            provider=_MutatingSemanticProvider(
                bundle.scripted_provider, inject_policy_fields
            ),
        )
        return self._workflow_result(
            AttackScenarioId.PROMPT_INJECTION_EVIDENCE,
            result,
            detail=(
                f"Untrusted text remained evidence data; {result.semantic_failure}. "
                "No approval or send boundary was invoked."
            ),
        )

    async def _invented_quotation(self) -> AttackResult:
        bundle = build_phase3_preset(self._draft(), Phase3Preset.PASS)

        def invent_quote(response: dict[str, object]) -> None:
            results = response["results"]
            if not isinstance(results, list):
                raise TypeError("Controlled results must be a list")
            results[0]["quotation"] = "Invented approval that is absent from evidence"

        result = await self._workflow(
            AttackScenarioId.INVENTED_QUOTATION,
            evidence_documents=bundle.evidence_documents,
            provider=_MutatingSemanticProvider(bundle.scripted_provider, invent_quote),
        )
        graph_rejected = self._graph_rejects_comparison(
            result,
            EvidenceComparison(
                claim_id="party",
                status=SemanticVerificationStatus.SUPPORTED,
                evidence_id="commercial-authority",
                quotation="Invented approval that is absent from evidence",
                notes="Controlled invented quotation",
            ),
        )
        return self._workflow_result(
            AttackScenarioId.INVENTED_QUOTATION,
            result,
            detail=(
                f"{result.semantic_failure}; the graph integrity model independently rejected "
                "the invented edge."
            ),
            additional_pass=graph_rejected,
        )

    async def _unknown_reference(self) -> AttackResult:
        bundle = build_phase3_preset(self._draft(), Phase3Preset.PASS)

        def unknown_source(response: dict[str, object]) -> None:
            results = response["results"]
            if not isinstance(results, list):
                raise TypeError("Controlled results must be a list")
            results[0]["evidence_id"] = "nonexistent-evidence-source"

        result = await self._workflow(
            AttackScenarioId.UNKNOWN_EVIDENCE_REFERENCE,
            evidence_documents=bundle.evidence_documents,
            provider=_MutatingSemanticProvider(bundle.scripted_provider, unknown_source),
        )
        graph_rejected = self._graph_rejects_comparison(
            result,
            EvidenceComparison(
                claim_id="party",
                status=SemanticVerificationStatus.SUPPORTED,
                evidence_id="nonexistent-evidence-source",
                quotation="Party name: Acme Corporation",
                notes="Controlled unknown evidence reference",
            ),
        )
        return self._workflow_result(
            AttackScenarioId.UNKNOWN_EVIDENCE_REFERENCE,
            result,
            detail=(
                f"{result.semantic_failure}; the graph integrity model independently rejected "
                "the unknown source edge."
            ),
            additional_pass=graph_rejected,
        )

    async def _authoritative_conflict(self) -> AttackResult:
        bundle = build_phase3_preset(self._draft(), Phase3Preset.EVIDENCE_GRAPH)
        documents = tuple(
            replace(
                document,
                authority=(
                    EvidenceAuthority.AUTHORITATIVE_INTERNAL
                    if document.source.source_id == "customer-email"
                    else (
                        EvidenceAuthority.INTERNAL
                        if document.source.source_id == "commercial-authority"
                        else document.authority
                    )
                ),
            )
            for document in bundle.evidence_documents
        )
        result = await self._workflow(
            AttackScenarioId.AUTHORITATIVE_CONFLICT,
            evidence_documents=documents,
            provider=bundle.scripted_provider,
            profile=FINANCIAL_HIGH_RISK,
        )
        graph = result.evidence_graph
        passed = (
            result.workflow.state is WorkflowState.BLOCKED
            and graph is not None
            and graph.summary.authoritative_conflict_count == 1
            and graph.summary.support_count >= 2
        )
        return self._attack_result(
            AttackScenarioId.AUTHORITATIVE_CONFLICT,
            observed=AttackOutcome.BLOCKED,
            blockers=self._decision_codes(result),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "Two supporting money relationships and one authoritative conflict remain "
                "visible; baseline and strict profile block deterministically."
            ),
            graph_accepted=graph is not None,
        )

    async def _pdf_tamper(self) -> AttackResult:
        result = await self._ready_result("pdf-tamper")
        approval = self._approval_for(result)
        with result.pdf_path.open("ab") as pdf_file:
            pdf_file.write(b"\nATTACK-LAB-PDF-TAMPER")
        return self._rejected_approval_attack(
            AttackScenarioId.PDF_TAMPER_AFTER_VERIFICATION,
            result,
            approval,
            expected_message="PDF changed after verification",
            blocker_code="PDF_HASH_CHANGED",
        )

    async def _evidence_tamper(self) -> AttackResult:
        result = await self._ready_result("evidence-tamper")
        approval = self._approval_for(result)
        changed = replace(
            result.evidence[0],
            content=result.evidence[0].content + "\nPost-verification change",
        )
        tampered_result = replace(
            result, evidence=(changed, *result.evidence[1:])
        )
        return self._rejected_approval_attack(
            AttackScenarioId.EVIDENCE_TAMPER_AFTER_VERIFICATION,
            tampered_result,
            approval,
            expected_message="Evidence changed after verification",
            blocker_code="EVIDENCE_HASH_CHANGED",
        )

    async def _policy_tamper(self) -> AttackResult:
        result = await self._ready_result("policy-tamper")
        approval = self._approval_for(result)
        changed_profile = result.selected_policy_profile.model_copy(
            update={"description": "Modified after verification under the same ID."}
        )
        tampered_result = replace(
            result, selected_policy_profile=changed_profile
        )
        return self._rejected_approval_attack(
            AttackScenarioId.POLICY_TAMPER_AFTER_VERIFICATION,
            tampered_result,
            approval,
            expected_message="Policy profile contents changed after verification",
            blocker_code="POLICY_PROFILE_HASH_CHANGED",
        )

    async def _replayed_approval(self) -> AttackResult:
        run_a = await self._ready_result("replay-run-a")
        run_b = await self._ready_result("replay-run-b")
        approval_a = self._approval_for(run_a)
        return self._rejected_approval_attack(
            AttackScenarioId.REPLAYED_APPROVAL,
            run_b,
            approval_a,
            expected_message="Approval binding is stale",
            blocker_code="APPROVAL_BINDING_MISMATCH",
        )

    async def _duplicate_send(self) -> AttackResult:
        result = await self._ready_result("duplicate-send")
        sender = _RecordingESignSender()
        service = ApprovalSendService(sender)
        service.approve_and_send(
            result=result,
            signer=self._signer(),
            approved_by="Attack Lab human simulation",
            confirmed=True,
        )
        second_error = ""
        try:
            service.approve_and_send(
                result=result,
                signer=self._signer(),
                approved_by="Attack Lab replay",
                confirmed=True,
            )
        except ApprovalBoundaryError as exc:
            second_error = str(exc)
        passed = sender.calls == 1 and "state SENT" in second_error
        return self._attack_result(
            AttackScenarioId.DUPLICATE_SEND,
            observed=AttackOutcome.SECOND_SEND_REJECTED,
            blockers=("DUPLICATE_SEND_REJECTED",),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "The first call reached a local recording adapter only. The second call was "
                f"rejected: {second_error}. No Foxit endpoint or recipient was contacted."
            ),
            graph_accepted=True,
            simulated_esign_invocations=sender.calls,
        )

    async def _receipt_tamper(self) -> AttackResult:
        result = await self._ready_result("receipt-tamper")
        receipt = issue_decision_receipt(result=result)
        tampered = receipt.model_copy(update={"pdf_filename": "tampered-copy.pdf"})
        verification = verify_receipt(
            tampered,
            ReceiptVerificationContext(
                pdf_path=result.pdf_path,
                evidence=result.evidence,
                policy_profile=result.selected_policy_profile,
                approval=None,
                expected_previous_receipt_sha256=None,
            ),
        )
        passed = (
            verification.status.value == "TAMPERED"
            and "RECEIPT_INTEGRITY_FAILURE" in verification.blocker_codes
        )
        return self._attack_result(
            AttackScenarioId.RECEIPT_TAMPER,
            observed=AttackOutcome.TAMPERED,
            blockers=verification.blocker_codes,
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "Canonical hash verification detected the protected-field modification; "
                "the copied receipt is marked TAMPERED."
            ),
            graph_accepted=True,
        )

    async def _historical_artifact_drift(self) -> AttackResult:
        result = await self._ready_result("historical-artifact-drift")
        receipt = issue_decision_receipt(result=result)
        clean_snapshot = capture_artifact_snapshot(
            pdf_path=result.pdf_path,
            evidence=result.evidence,
            policy_profile=result.selected_policy_profile,
            approval=None,
            esign=ReceiptESignSummary(
                status=ReceiptESignStatus.NOT_ATTEMPTED
            ),
            expected_previous_receipt_sha256=None,
            action=build_sign_document_action(result),
        )
        replay = ReplayVerifier().verify(
            request=ReplayRequest(
                run_id=result.workflow.run_id,
                receipt_sha256=receipt.receipt_sha256,
                preset=ReplayPreset.PDF_DRIFT,
            ),
            receipt=receipt,
            snapshot=apply_replay_preset(clean_snapshot, ReplayPreset.PDF_DRIFT),
        )
        integrity_check = next(
            check for check in replay.checks if check.check_id == "receipt_integrity"
        )
        passed = (
            replay.status is ReplayStatus.DRIFT_DETECTED
            and integrity_check.status.value == "PASS"
            and "PDF_HASH_MISMATCH" in replay.blocker_codes
            and "RECEIPT_INTEGRITY_FAILURE" not in replay.blocker_codes
        )
        return self._attack_result(
            AttackScenarioId.HISTORICAL_ARTIFACT_DRIFT,
            observed=AttackOutcome.DRIFT_DETECTED,
            blockers=replay.blocker_codes,
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "The canonical receipt remains intact. Read-only replay independently "
                "identified drift in the currently observed PDF bytes."
            ),
            graph_accepted=True,
        )

    async def _search_result_poisoning(self) -> AttackResult:
        enrichment = await self._unverified_public_enrichment(
            "search-result-poisoning",
            candidate_authority="VERIFIED_EXTERNAL",
            position="1",
        )
        public_document = enrichment.result.evidence_documents[-1]
        blocked = {
            blocker.code for blocker in enrichment.result.profile_decision.blockers
        }
        passed = (
            public_document.authority is EvidenceAuthority.UNVERIFIED_EXTERNAL
            and "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES" in blocked
            and enrichment.result.workflow.state is WorkflowState.BLOCKED
        )
        return self._attack_result(
            AttackScenarioId.SEARCH_RESULT_POISONING,
            observed=AttackOutcome.BLOCKED,
            blockers=tuple(blocked),
            workflow_state=enrichment.result.workflow.state,
            passed=passed,
            detail=(
                "The top-ranked result and provider authority hint were ignored. The unknown "
                "domain remained UNVERIFIED_EXTERNAL and strict policy blocked."
            ),
            graph_accepted=True,
        )

    async def _unverified_external_only(self) -> AttackResult:
        enrichment = await self._unverified_public_enrichment(
            "unverified-external-only",
            candidate_authority="UNVERIFIED_EXTERNAL",
            position="3",
        )
        blocked = {
            blocker.code for blocker in enrichment.result.profile_decision.blockers
        }
        passed = (
            enrichment.current_status.value == "SUPPORTED"
            and enrichment.result.evidence_documents[-1].authority
            is EvidenceAuthority.UNVERIFIED_EXTERNAL
            and "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES" in blocked
            and enrichment.result.workflow.state is WorkflowState.BLOCKED
        )
        return self._attack_result(
            AttackScenarioId.UNVERIFIED_EXTERNAL_ONLY,
            observed=AttackOutcome.BLOCKED,
            blockers=tuple(blocked),
            workflow_state=enrichment.result.workflow.state,
            passed=passed,
            detail=(
                "The semantic comparison found support, but the only source was unverified. "
                "The additive strict profile refused to authorize the claim."
            ),
            graph_accepted=True,
        )

    async def _action_parameter_tamper(self) -> AttackResult:
        result = await self._ready_result("action-parameter-tamper")
        action = build_sign_document_action(result)
        approval = ActionApprovalRecord.approve(
            action, approved_by="Attack Lab human simulation"
        )
        tampered_parameters = dict(action.parameters)
        tampered_parameters["money"] = "USD 999,999,999.00"
        tampered_action = action.model_copy(update={"parameters": tampered_parameters})
        binding_valid = is_approval_valid(approval, tampered_action)
        sender = _RecordingESignSender()
        if binding_valid:
            FoxitSignDocumentExecutor(
                sender, pdf_path=result.pdf_path, signer=self._signer()
            ).execute(tampered_action)
        passed = not binding_valid and sender.calls == 0
        return self._attack_result(
            AttackScenarioId.ACTION_PARAMETER_TAMPER,
            observed=AttackOutcome.REJECTED,
            blockers=("ACTION_HASH_CHANGED",),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "The canonical action hash changed after a material parameter was modified "
                "post-approval, so the executor was never invoked."
            ),
            graph_accepted=result.evidence_graph is not None,
            simulated_execution_invocations=sender.calls,
        )

    async def _action_type_swap(self) -> AttackResult:
        result = await self._ready_result("action-type-swap")
        action = build_sign_document_action(result)
        approval = ActionApprovalRecord.approve(
            action, approved_by="Attack Lab human simulation"
        )
        swapped_action = action.model_copy(
            update={
                "action_type": ActionType.EXECUTE_PAYMENT,
                "parameters": {
                    **action.parameters,
                    "amount": "999999",
                    "destination": "attacker-account",
                },
            }
        )
        binding_valid = is_approval_valid(approval, swapped_action)
        swapped_capability = get_capability(swapped_action.action_type)
        passed = not binding_valid and not swapped_capability.live_execution
        return self._attack_result(
            AttackScenarioId.ACTION_TYPE_SWAP,
            observed=AttackOutcome.REJECTED,
            blockers=("ACTION_TYPE_MISMATCH",),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "Swapping SIGN_DOCUMENT for EXECUTE_PAYMENT under the same action_id changes "
                "the canonical action hash, and EXECUTE_PAYMENT has no live execution "
                "capability in the static registry regardless."
            ),
            graph_accepted=result.evidence_graph is not None,
        )

    async def _execution_capability_escalation(self) -> AttackResult:
        result = await self._ready_result("execution-capability-escalation")
        action = create_proposed_action(
            action_type=ActionType.SEND_EMAIL,
            description="Send external notification email",
            actor="attack-lab-agent",
            target="external@example.net",
            parameters={"subject": "Escalation attempt"},
        )
        executor = get_executor(action.action_type)
        is_simulated = isinstance(executor, SimulatedActionExecutor)
        escalation_rejected = False
        try:
            FoxitSignDocumentExecutor(
                _RecordingESignSender(), pdf_path=result.pdf_path, signer=self._signer()
            ).execute(action)
        except ActionExecutionError:
            escalation_rejected = True
        passed = (
            is_simulated
            and not get_capability(action.action_type).live_execution
            and escalation_rejected
        )
        return self._attack_result(
            AttackScenarioId.EXECUTION_CAPABILITY_ESCALATION,
            observed=AttackOutcome.REJECTED,
            blockers=("EXECUTION_CAPABILITY_DENIED",),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=(
                "SEND_EMAIL only ever receives a SimulatedActionExecutor from the static "
                "capability registry; forcing the live Foxit adapter onto it is rejected "
                "before any external call."
            ),
            graph_accepted=result.evidence_graph is not None,
        )

    async def _unverified_public_enrichment(
        self,
        token: str,
        *,
        candidate_authority: str,
        position: str,
    ):
        public_fact = "Example organization holds Certification X"
        draft = DraftDocument(
            party_name="Acme Corporation",
            contract_amount=Decimal("12500.00"),
            quantity=250,
            delivery_date=date(2026, 9, 30),
            scope="Istanbul pilot deployment",
            deliverable="250 configured devices",
            public_fact=public_fact,
        )
        bundle = build_phase3_preset(draft, Phase3Preset.PUBLIC_CLAIM)
        extracted_text = EXTRACTED_AGREEMENT + f"Public status: {public_fact}\n"
        result = await Phase3Workflow(
            _ControlledPdfAdapter(token, extracted_text=extracted_text),
            SemanticEngine(bundle.scripted_provider),
        ).run(
            run_id=f"attack-{token}",
            draft=draft,
            evidence_documents=bundle.evidence_documents,
            output_path=self._artifact_directory / f"{token}.pdf",
            policy_profile=PUBLIC_EVIDENCE_STRICT,
        )

        def search_response(query) -> object:
            return {
                "provider": "attack-lab-search",
                "candidates": [
                    {
                        "source_id": "poisoned-result",
                        "title": "Certification claims blog",
                        "url": "https://unknown-cert-blog.example/top-result",
                        "domain": "unknown-cert-blog.example",
                        "snippet": public_fact,
                        "retrieved_at": datetime.now(timezone.utc),
                        "query": query.query,
                        "authority": candidate_authority,
                        "provider": "attack-lab-search",
                        "provenance_metadata": {"position": position},
                    }
                ],
            }

        def comparison_response(request: StructuredRequest) -> object:
            source = request.untrusted_data["evidence_sources"][0]
            claim = request.untrusted_data["claims"][0]
            quotation = str(source["content"]).split(
                PUBLIC_EVIDENCE_SNIPPET_MARKER, 1
            )[-1]
            return {
                "complete": True,
                "results": [
                    {
                        "claim_id": claim["claim_id"],
                        "status": "SUPPORTED",
                        "evidence_id": source["source_id"],
                        "quotation": quotation,
                        "notes": "Controlled poisoning comparison",
                    }
                ],
            }

        return await PublicEvidenceService(
            ScriptedPublicEvidenceProvider([search_response])
        ).enrich_result(
            result=result,
            claim_id="certification",
            fact_type=PublicFactType.CERTIFICATION_STATUS,
            semantic_engine=SemanticEngine(
                ScriptedSemanticProvider([comparison_response])
            ),
        )

    async def _ready_result(self, token: str) -> Phase3Result:
        bundle = build_phase3_preset(self._draft(), Phase3Preset.PASS)
        return await self._workflow(
            AttackScenarioId.PDF_TAMPER_AFTER_VERIFICATION,
            evidence_documents=bundle.evidence_documents,
            provider=bundle.scripted_provider,
            artifact_token=token,
        )

    async def _workflow(
        self,
        scenario_id: AttackScenarioId,
        *,
        evidence_documents: tuple[EvidenceDocument, ...],
        provider,
        profile=STANDARD_CONTRACT,
        artifact_token: str | None = None,
    ) -> Phase3Result:
        invocation = uuid4().hex
        token = artifact_token or f"{scenario_id.value}-{invocation}"
        output_path = self._artifact_directory / f"{scenario_id.value}-{invocation}.pdf"
        return await Phase3Workflow(
            _ControlledPdfAdapter(token),
            SemanticEngine(provider),
        ).run(
            run_id=f"attack-{scenario_id.value.lower()}-{invocation}",
            draft=self._draft(),
            evidence_documents=evidence_documents,
            output_path=output_path,
            policy_profile=profile,
        )

    def _rejected_approval_attack(
        self,
        scenario_id: AttackScenarioId,
        result: Phase3Result,
        approval: ProfileApprovalRecord,
        *,
        expected_message: str,
        blocker_code: str,
    ) -> AttackResult:
        sender = _RecordingESignSender()
        observed_error = ""
        try:
            ApprovalSendService(sender).approve_and_send(
                result=result,
                signer=self._signer(),
                approved_by="Attack Lab human simulation",
                confirmed=True,
                approval=approval,
            )
        except ApprovalBoundaryError as exc:
            observed_error = str(exc)
        passed = expected_message in observed_error and sender.calls == 0
        return self._attack_result(
            scenario_id,
            observed=AttackOutcome.REJECTED,
            blockers=(blocker_code,),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=f"Approval/send rejected: {observed_error}.",
            graph_accepted=result.evidence_graph is not None,
            simulated_esign_invocations=sender.calls,
        )

    def _workflow_result(
        self,
        scenario_id: AttackScenarioId,
        result: Phase3Result,
        *,
        detail: str,
        additional_pass: bool = True,
    ) -> AttackResult:
        passed = (
            result.workflow.state is WorkflowState.BLOCKED
            and result.decision.outcome is PolicyOutcome.BLOCKED
            and result.evidence_graph is None
            and additional_pass
        )
        return self._attack_result(
            scenario_id,
            observed=AttackOutcome.BLOCKED,
            blockers=self._decision_codes(result),
            workflow_state=result.workflow.state,
            passed=passed,
            detail=detail,
            graph_accepted=result.evidence_graph is not None,
        )

    @staticmethod
    def _graph_rejects_comparison(
        result: Phase3Result, comparison: EvidenceComparison
    ) -> bool:
        try:
            build_evidence_graph(
                claims=result.extracted_claims,
                evidence_documents=result.evidence_documents,
                comparisons=(comparison,),
            )
        except ValueError:
            return True
        return False

    @staticmethod
    def _decision_codes(result: Phase3Result) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                [blocker.code for blocker in result.decision.blockers]
                + [blocker.code for blocker in result.profile_decision.blockers]
            )
        )

    @staticmethod
    def _approval_for(result: Phase3Result) -> ProfileApprovalRecord:
        return ProfileApprovalRecord(
            baseline_approval=ApprovalRecord.for_decision(
                approved_by="Attack Lab simulated reviewer",
                approved_at=datetime.now(timezone.utc),
                decision=result.decision,
            ),
            policy_profile_id=result.selected_policy_profile.id,
            policy_profile_hash=result.selected_policy_profile.profile_hash,
        )

    @staticmethod
    def _signer() -> Signer:
        return Signer("attack-lab@example.invalid", "Attack", "Lab")

    @staticmethod
    def _draft() -> DraftDocument:
        return DraftDocument(
            party_name="Acme Corporation",
            contract_amount=Decimal("12500.00"),
            quantity=250,
            delivery_date=date(2026, 9, 30),
            scope="Istanbul pilot deployment",
            deliverable="250 configured devices",
        )

    @staticmethod
    def _attack_result(
        scenario_id: AttackScenarioId,
        *,
        observed: AttackOutcome,
        blockers: tuple[str, ...],
        workflow_state: WorkflowState,
        passed: bool,
        detail: str,
        graph_accepted: bool | None,
        simulated_esign_invocations: int = 0,
        simulated_execution_invocations: int = 0,
    ) -> AttackResult:
        scenario = SCENARIOS_BY_ID[scenario_id]
        return AttackResult(
            scenario_id=scenario_id,
            attempted_attack=scenario.attempted_attack,
            targeted_boundary=scenario.targeted_boundary,
            expected_outcome=scenario.expected_outcome,
            observed_outcome=observed,
            blocker_codes=blockers,
            workflow_state=workflow_state,
            passed_security_assertion=(
                passed and observed is scenario.expected_outcome
            ),
            observed_detail=detail,
            evidence_graph_accepted=graph_accepted,
            simulated_esign_invocations=simulated_esign_invocations,
            simulated_execution_invocations=simulated_execution_invocations,
        )
