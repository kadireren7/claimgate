"""Typed Attack Lab catalog and result contracts."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from claimgate.domain import WorkflowState


class StrictAttackModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class AttackScenarioId(str, Enum):
    PROMPT_INJECTION_EVIDENCE = "PROMPT_INJECTION_EVIDENCE"
    INVENTED_QUOTATION = "INVENTED_QUOTATION"
    UNKNOWN_EVIDENCE_REFERENCE = "UNKNOWN_EVIDENCE_REFERENCE"
    AUTHORITATIVE_CONFLICT = "AUTHORITATIVE_CONFLICT"
    PDF_TAMPER_AFTER_VERIFICATION = "PDF_TAMPER_AFTER_VERIFICATION"
    EVIDENCE_TAMPER_AFTER_VERIFICATION = "EVIDENCE_TAMPER_AFTER_VERIFICATION"
    POLICY_TAMPER_AFTER_VERIFICATION = "POLICY_TAMPER_AFTER_VERIFICATION"
    REPLAYED_APPROVAL = "REPLAYED_APPROVAL"
    DUPLICATE_SEND = "DUPLICATE_SEND"
    RECEIPT_TAMPER = "RECEIPT_TAMPER"
    HISTORICAL_ARTIFACT_DRIFT = "HISTORICAL_ARTIFACT_DRIFT"
    SEARCH_RESULT_POISONING = "SEARCH_RESULT_POISONING"
    UNVERIFIED_EXTERNAL_ONLY = "UNVERIFIED_EXTERNAL_ONLY"
    ACTION_PARAMETER_TAMPER = "ACTION_PARAMETER_TAMPER"
    ACTION_TYPE_SWAP = "ACTION_TYPE_SWAP"
    EXECUTION_CAPABILITY_ESCALATION = "EXECUTION_CAPABILITY_ESCALATION"


class AttackOutcome(str, Enum):
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    SECOND_SEND_REJECTED = "SECOND_SEND_REJECTED"
    TAMPERED = "TAMPERED"
    DRIFT_DETECTED = "DRIFT_DETECTED"


class AttackScenario(StrictAttackModel):
    scenario_id: AttackScenarioId = Field(strict=False)
    name: str = Field(min_length=1, max_length=100)
    attempted_attack: str = Field(min_length=1, max_length=500)
    targeted_boundary: str = Field(min_length=1, max_length=160)
    expected_invariant: str = Field(min_length=1, max_length=500)
    expected_outcome: AttackOutcome = Field(strict=False)
    untrusted_evidence: str | None = Field(default=None, max_length=2000)


class SecurityAssertion(StrictAttackModel):
    assertion_id: str = Field(min_length=1, max_length=80)
    statement: str = Field(min_length=1, max_length=300)
    passed: bool
    observed_evidence: str = Field(min_length=1, max_length=500)


class AttackResult(StrictAttackModel):
    scenario_id: AttackScenarioId = Field(strict=False)
    attempted_attack: str
    targeted_boundary: str
    expected_outcome: AttackOutcome = Field(strict=False)
    observed_outcome: AttackOutcome = Field(strict=False)
    blocker_codes: tuple[str, ...]
    workflow_state: WorkflowState = Field(strict=False)
    passed_security_assertion: bool
    observed_detail: str = Field(min_length=1, max_length=1000)
    evidence_graph_accepted: bool | None = None
    simulated_esign_invocations: int = Field(default=0, ge=0, le=1)
    simulated_execution_invocations: int = Field(default=0, ge=0, le=1)
