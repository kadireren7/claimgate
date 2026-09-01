from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from claimgate.actions import (
    CAPABILITY_REGISTRY,
    ActionApprovalRecord,
    ActionExecutionError,
    ActionRisk,
    ActionType,
    FoxitSignDocumentExecutor,
    ProposedAction,
    SimulatedActionExecutor,
    action_sha256,
    authorize_action,
    create_proposed_action,
    get_executor,
    is_approval_valid,
)
from claimgate.domain import PolicyOutcome
from claimgate.integrations.foxit_esign import ESignSendResult, Signer


def _sign_document_action(**overrides: object) -> ProposedAction:
    defaults: dict[str, object] = {
        "action_type": ActionType.SIGN_DOCUMENT,
        "description": "Sign and send the agreement",
        "actor": "claimgate-demo-agent",
        "target": "Acme Corporation",
        "parameters": {"money": "USD 12,500.00", "party_identity": "Acme Corporation"},
        "artifact_sha256": ("a" * 64,),
        "evidence_sha256": "b" * 64,
        "baseline_policy_version": "claimgate-policy-v1",
        "policy_profile_id": "standard-contract-v1",
        "policy_profile_sha256": "c" * 64,
        "action_id": "run-fixed-action",
        "created_at": datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc),
    }
    defaults.update(overrides)
    return create_proposed_action(**defaults)  # type: ignore[arg-type]


def test_action_sha256_is_deterministic() -> None:
    first = _sign_document_action()
    second = _sign_document_action()

    assert action_sha256(first) == action_sha256(second)


def test_action_sha256_changes_with_material_parameter_change() -> None:
    original = _sign_document_action()
    changed = _sign_document_action(parameters={"money": "USD 999,999.00"})

    assert action_sha256(original) != action_sha256(changed)


def test_action_type_change_invalidates_approval() -> None:
    action = _sign_document_action()
    approval = ActionApprovalRecord.approve(action, approved_by="human")
    swapped = action.model_copy(update={"action_type": ActionType.EXECUTE_PAYMENT})

    assert is_approval_valid(approval, action) is True
    assert is_approval_valid(approval, swapped) is False


def test_target_change_invalidates_approval() -> None:
    action = _sign_document_action()
    approval = ActionApprovalRecord.approve(action, approved_by="human")
    retargeted = action.model_copy(update={"target": "A Different Counterparty"})

    assert is_approval_valid(approval, retargeted) is False


def test_risk_level_is_application_controlled() -> None:
    with pytest.raises(ValidationError):
        ProposedAction(
            action_id="bad-risk",
            action_type=ActionType.SIGN_DOCUMENT,
            description="d",
            actor="a",
            target="t",
            parameters={},
            risk=ActionRisk.LOW,
            artifact_sha256=(),
            evidence_sha256=None,
            baseline_policy_version=None,
            policy_profile_id=None,
            policy_profile_sha256=None,
            created_at=datetime.now(timezone.utc),
        )

    action = _sign_document_action()
    assert action.risk is ActionRisk.IRREVERSIBLE


def test_capability_registry_is_static_and_only_sign_document_is_live() -> None:
    assert set(CAPABILITY_REGISTRY) == set(ActionType)
    live_types = {
        action_type
        for action_type, capability in CAPABILITY_REGISTRY.items()
        if capability.live_execution
    }
    assert live_types == {ActionType.SIGN_DOCUMENT}
    assert CAPABILITY_REGISTRY[ActionType.SIGN_DOCUMENT].adapter == "FOXIT_ESIGN"
    for action_type, capability in CAPABILITY_REGISTRY.items():
        if action_type is not ActionType.SIGN_DOCUMENT:
            assert capability.adapter == "SIMULATED"


def test_get_executor_returns_simulated_for_every_type_except_sign_document() -> None:
    for action_type in ActionType:
        if action_type is ActionType.SIGN_DOCUMENT:
            continue
        assert isinstance(get_executor(action_type), SimulatedActionExecutor)


def test_only_sign_document_can_reach_foxit_adapter(tmp_path: Path) -> None:
    class RecordingSender:
        def __init__(self) -> None:
            self.calls = 0

        def send_pdf_for_signature(self, pdf_path: Path, signer: Signer) -> ESignSendResult:
            self.calls += 1
            return ESignSendResult(folder_id="test-folder")

    pdf_path = tmp_path / "agreement.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\ntest")
    sender = RecordingSender()
    signer = Signer("recipient@example.com", "Test", "Signer")
    executor = get_executor(
        ActionType.SIGN_DOCUMENT, sender=sender, pdf_path=pdf_path, signer=signer
    )
    assert isinstance(executor, FoxitSignDocumentExecutor)

    result = executor.execute(_sign_document_action())
    assert result.status == "EXECUTED"
    assert result.external_identifier == "test-folder"
    assert sender.calls == 1

    with pytest.raises(ActionExecutionError):
        executor.execute(
            create_proposed_action(
                action_type=ActionType.SEND_EMAIL,
                description="d",
                actor="a",
                target="t",
                created_at=datetime.now(timezone.utc),
            )
        )
    assert sender.calls == 1


def test_simulated_executor_rejects_a_live_execution_type() -> None:
    executor = SimulatedActionExecutor()
    with pytest.raises(ActionExecutionError):
        executor.execute(_sign_document_action())
    assert executor.calls == []


def test_simulated_action_cannot_access_live_adapter() -> None:
    for action_type in ActionType:
        if action_type is ActionType.SIGN_DOCUMENT:
            continue
        executor = get_executor(action_type)
        assert not isinstance(executor, FoxitSignDocumentExecutor)
        result = executor.execute(
            create_proposed_action(
                action_type=action_type,
                description="d",
                actor="a",
                target="t",
                created_at=datetime.now(timezone.utc),
            )
        )
        assert result.status == "SIMULATED"
        assert "SIMULATION ONLY" in result.detail


@pytest.mark.parametrize(
    ("action_type", "parameters", "expected_codes"),
    [
        (
            ActionType.EXECUTE_PAYMENT,
            {},
            {
                "ACTION_PAYMENT_AMOUNT_REQUIRED",
                "ACTION_PAYMENT_DESTINATION_REQUIRED",
                "ACTION_AUTHORITATIVE_EVIDENCE_REQUIRED",
            },
        ),
        (
            ActionType.DEPLOY_SOFTWARE,
            {},
            {"ACTION_DEPLOY_REVISION_REQUIRED", "ACTION_DEPLOY_ENVIRONMENT_REQUIRED"},
        ),
    ],
)
def test_authorize_action_blocks_missing_action_specific_requirements(
    action_type: ActionType, parameters: dict[str, str], expected_codes: set[str]
) -> None:
    action = create_proposed_action(
        action_type=action_type,
        description="d",
        actor="a",
        target="t",
        parameters=parameters,
        created_at=datetime.now(timezone.utc),
    )

    decision = authorize_action(action)

    assert decision.outcome is PolicyOutcome.BLOCKED
    assert {blocker.code for blocker in decision.blockers} == expected_codes


def test_authorize_action_passes_when_sign_document_bindings_are_present() -> None:
    decision = authorize_action(_sign_document_action())

    assert decision.outcome is PolicyOutcome.READY_FOR_APPROVAL
    assert decision.blockers == ()
    assert decision.execution_capability.live_execution is True


def test_authorize_action_blocks_sign_document_missing_bindings() -> None:
    action = _sign_document_action(
        artifact_sha256=(), evidence_sha256=None, policy_profile_id=None, policy_profile_sha256=None
    )

    decision = authorize_action(action)

    assert decision.outcome is PolicyOutcome.BLOCKED
    codes = {blocker.code for blocker in decision.blockers}
    assert codes == {
        "ACTION_ARTIFACT_HASH_REQUIRED",
        "ACTION_EVIDENCE_HASH_REQUIRED",
        "ACTION_POLICY_PROFILE_REQUIRED",
    }


def test_semantic_package_has_no_import_of_actions_package() -> None:
    package_directory = Path(__file__).parents[1] / "src" / "claimgate" / "semantic"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in package_directory.glob("*.py")
    )

    assert "claimgate.actions" not in source


def test_actions_registry_module_has_no_registration_function() -> None:
    source = (
        Path(__file__).parents[1] / "src" / "claimgate" / "actions" / "registry.py"
    ).read_text(encoding="utf-8")

    assert "def register" not in source
