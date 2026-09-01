from __future__ import annotations

from pathlib import Path

import pytest

from claimgate.domain import WorkflowState
from claimgate.redteam import (
    ATTACK_SCENARIOS,
    PROMPT_INJECTION_TEXT,
    AttackOutcome,
    AttackRunner,
    AttackScenarioId,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ATTACK_SCENARIOS, ids=lambda item: item.scenario_id.value)
async def test_every_attack_scenario_enforces_expected_boundary(
    tmp_path: Path, scenario
) -> None:
    result = await AttackRunner(tmp_path / "attack-artifacts").run(
        scenario.scenario_id
    )

    assert result.expected_outcome is scenario.expected_outcome
    assert result.observed_outcome is scenario.expected_outcome
    assert result.passed_security_assertion is True
    assert result.blocker_codes
    assert result.simulated_esign_invocations <= 1
    assert result.simulated_execution_invocations <= 1


@pytest.mark.asyncio
async def test_action_parameter_tamper_scenario_rejected_with_zero_executions(
    tmp_path: Path,
) -> None:
    result = await AttackRunner(tmp_path / "attack-artifacts").run(
        AttackScenarioId.ACTION_PARAMETER_TAMPER
    )

    assert result.observed_outcome is AttackOutcome.REJECTED
    assert "ACTION_HASH_CHANGED" in result.blocker_codes
    assert result.simulated_execution_invocations == 0
    assert result.passed_security_assertion is True


@pytest.mark.asyncio
async def test_action_type_swap_scenario_rejected(tmp_path: Path) -> None:
    result = await AttackRunner(tmp_path / "attack-artifacts").run(
        AttackScenarioId.ACTION_TYPE_SWAP
    )

    assert result.observed_outcome is AttackOutcome.REJECTED
    assert "ACTION_TYPE_MISMATCH" in result.blocker_codes
    assert result.passed_security_assertion is True


@pytest.mark.asyncio
async def test_execution_capability_escalation_scenario_rejected(tmp_path: Path) -> None:
    result = await AttackRunner(tmp_path / "attack-artifacts").run(
        AttackScenarioId.EXECUTION_CAPABILITY_ESCALATION
    )

    assert result.observed_outcome is AttackOutcome.REJECTED
    assert "EXECUTION_CAPABILITY_DENIED" in result.blocker_codes
    assert result.passed_security_assertion is True


@pytest.mark.asyncio
async def test_prompt_injection_is_untrusted_and_cannot_sign_or_transition(
    tmp_path: Path,
) -> None:
    scenario = next(
        item
        for item in ATTACK_SCENARIOS
        if item.scenario_id is AttackScenarioId.PROMPT_INJECTION_EVIDENCE
    )
    result = await AttackRunner(tmp_path).run(scenario.scenario_id)

    assert scenario.untrusted_evidence == PROMPT_INJECTION_TEXT
    assert "Approve and send" in scenario.untrusted_evidence
    assert result.observed_outcome is AttackOutcome.BLOCKED
    assert result.workflow_state is WorkflowState.BLOCKED
    assert result.evidence_graph_accepted is False
    assert result.simulated_esign_invocations == 0
    assert "VERIFICATION_FAILED" in result.blocker_codes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_id",
    [
        AttackScenarioId.INVENTED_QUOTATION,
        AttackScenarioId.UNKNOWN_EVIDENCE_REFERENCE,
    ],
)
async def test_invalid_semantic_evidence_cannot_create_graph_edges(
    tmp_path: Path, scenario_id: AttackScenarioId
) -> None:
    result = await AttackRunner(tmp_path).run(scenario_id)

    assert result.workflow_state is WorkflowState.BLOCKED
    assert result.evidence_graph_accepted is False
    assert "graph integrity model independently rejected" in result.observed_detail
    assert result.simulated_esign_invocations == 0


@pytest.mark.asyncio
async def test_authoritative_conflict_remains_visible_and_blocks(tmp_path: Path) -> None:
    result = await AttackRunner(tmp_path).run(
        AttackScenarioId.AUTHORITATIVE_CONFLICT
    )

    assert result.evidence_graph_accepted is True
    assert result.workflow_state is WorkflowState.BLOCKED
    assert "CRITICAL_CLAIM_CONFLICTING" in result.blocker_codes
    assert "PROFILE_CONFLICT_NOT_ALLOWED" in result.blocker_codes
    assert "authoritative conflict remain visible" in result.observed_detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario_id", "expected_code"),
    [
        (AttackScenarioId.PDF_TAMPER_AFTER_VERIFICATION, "PDF_HASH_CHANGED"),
        (
            AttackScenarioId.EVIDENCE_TAMPER_AFTER_VERIFICATION,
            "EVIDENCE_HASH_CHANGED",
        ),
        (
            AttackScenarioId.POLICY_TAMPER_AFTER_VERIFICATION,
            "POLICY_PROFILE_HASH_CHANGED",
        ),
        (AttackScenarioId.REPLAYED_APPROVAL, "APPROVAL_BINDING_MISMATCH"),
    ],
)
async def test_bound_approval_attacks_never_reach_sender(
    tmp_path: Path, scenario_id: AttackScenarioId, expected_code: str
) -> None:
    result = await AttackRunner(tmp_path).run(scenario_id)

    assert result.observed_outcome is AttackOutcome.REJECTED
    assert result.workflow_state is WorkflowState.READY_FOR_APPROVAL
    assert result.blocker_codes == (expected_code,)
    assert result.simulated_esign_invocations == 0


@pytest.mark.asyncio
async def test_duplicate_send_reaches_local_adapter_at_most_once(tmp_path: Path) -> None:
    result = await AttackRunner(tmp_path).run(AttackScenarioId.DUPLICATE_SEND)

    assert result.observed_outcome is AttackOutcome.SECOND_SEND_REJECTED
    assert result.workflow_state is WorkflowState.SENT
    assert result.simulated_esign_invocations == 1
    assert result.blocker_codes == ("DUPLICATE_SEND_REJECTED",)
    assert "No Foxit endpoint or recipient was contacted" in result.observed_detail


@pytest.mark.asyncio
async def test_receipt_tamper_is_detected_by_canonical_integrity_check(
    tmp_path: Path,
) -> None:
    result = await AttackRunner(tmp_path).run(AttackScenarioId.RECEIPT_TAMPER)

    assert result.observed_outcome is AttackOutcome.TAMPERED
    assert result.workflow_state is WorkflowState.READY_FOR_APPROVAL
    assert "RECEIPT_INTEGRITY_FAILURE" in result.blocker_codes
    assert result.simulated_esign_invocations == 0


@pytest.mark.asyncio
async def test_historical_drift_keeps_receipt_integrity_distinct(
    tmp_path: Path,
) -> None:
    result = await AttackRunner(tmp_path).run(
        AttackScenarioId.HISTORICAL_ARTIFACT_DRIFT
    )

    assert result.observed_outcome is AttackOutcome.DRIFT_DETECTED
    assert result.workflow_state is WorkflowState.READY_FOR_APPROVAL
    assert result.blocker_codes == ("PDF_HASH_MISMATCH",)
    assert "canonical receipt remains intact" in result.observed_detail
    assert result.simulated_esign_invocations == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario_id",
    [
        AttackScenarioId.SEARCH_RESULT_POISONING,
        AttackScenarioId.UNVERIFIED_EXTERNAL_ONLY,
    ],
)
async def test_public_search_attacks_cannot_promote_or_authorize_unknown_sources(
    tmp_path: Path, scenario_id: AttackScenarioId
) -> None:
    result = await AttackRunner(tmp_path).run(scenario_id)

    assert result.observed_outcome is AttackOutcome.BLOCKED
    assert result.workflow_state is WorkflowState.BLOCKED
    assert "PROFILE_INSUFFICIENT_AUTHORITATIVE_SOURCES" in result.blocker_codes
    assert result.simulated_esign_invocations == 0


def test_attack_runner_uses_application_boundaries_not_private_state_or_live_clients() -> None:
    runner_source = (
        Path(__file__).parents[1]
        / "src"
        / "claimgate"
        / "redteam"
        / "runner.py"
    ).read_text(encoding="utf-8")

    assert "ApprovalSendService" in runner_source
    assert "Phase3Workflow" in runner_source
    assert "._state" not in runner_source
    assert "import FoxitESignClient" not in runner_source
    assert "import FoxitPdfClient" not in runner_source
    assert "subprocess" not in runner_source
    assert "eval(" not in runner_source
    assert "exec(" not in runner_source


def test_computed_security_invariants_all_hold(tmp_path: Path) -> None:
    assertions = AttackRunner(tmp_path).security_invariants()

    assert len(assertions) == 8
    assert all(assertion.passed for assertion in assertions)
    assert {assertion.assertion_id for assertion in assertions} == {
        "SEMANTIC_NO_ESIGN",
        "EVIDENCE_NO_POLICY_MUTATION",
        "EVIDENCE_NO_WORKFLOW_MUTATION",
        "BROWSER_NO_FOXIT_CREDENTIALS",
        "APPROVAL_ARTIFACT_BOUND",
        "PROFILE_CANNOT_WEAKEN_BASELINE",
        "ACTION_REGISTRY_IS_STATIC",
        "SEMANTIC_HAS_NO_ACTION_IMPORT",
    }
