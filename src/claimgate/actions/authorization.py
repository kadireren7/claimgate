"""Canonical action hashing and deterministic, action-type-specific authorization.

Requirement checks below are hardcoded per ActionType, never configurable by a
caller, browser request, or semantic provider.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from types import MappingProxyType

from claimgate.actions.models import (
    ActionType,
    AuthorizationBlocker,
    AuthorizationDecision,
    ProposedAction,
)
from claimgate.actions.registry import get_capability
from claimgate.domain.models import PolicyOutcome


def canonical_action_json(action: ProposedAction) -> str:
    """Canonical, deterministically ordered JSON of every material action field.

    ``created_at`` is deliberately excluded (a wall-clock timestamp is not a
    material action parameter); no mutable execution status field exists on
    ProposedAction at all, so there is nothing else to exclude.
    """

    payload = {
        "action_id": action.action_id,
        "action_type": action.action_type.value,
        "description": action.description,
        "actor": action.actor,
        "target": action.target,
        "parameters": action.parameters,
        "risk": action.risk.value,
        "artifact_sha256": sorted(action.artifact_sha256),
        "evidence_sha256": action.evidence_sha256,
        "baseline_policy_version": action.baseline_policy_version,
        "policy_profile_id": action.policy_profile_id,
        "policy_profile_sha256": action.policy_profile_sha256,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def action_sha256(action: ProposedAction) -> str:
    return hashlib.sha256(canonical_action_json(action).encode("utf-8")).hexdigest()


def _check_sign_document(action: ProposedAction) -> list[AuthorizationBlocker]:
    blockers: list[AuthorizationBlocker] = []
    if not action.artifact_sha256:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_ARTIFACT_HASH_REQUIRED",
                message="SIGN_DOCUMENT requires a final PDF hash",
            )
        )
    if action.evidence_sha256 is None:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_EVIDENCE_HASH_REQUIRED",
                message="SIGN_DOCUMENT requires an evidence hash",
            )
        )
    if action.policy_profile_id is None or action.policy_profile_sha256 is None:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_POLICY_PROFILE_REQUIRED",
                message="SIGN_DOCUMENT requires a bound policy profile",
            )
        )
    return blockers


def _check_execute_payment(action: ProposedAction) -> list[AuthorizationBlocker]:
    blockers: list[AuthorizationBlocker] = []
    if "amount" not in action.parameters:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_PAYMENT_AMOUNT_REQUIRED",
                message="EXECUTE_PAYMENT requires an amount parameter",
            )
        )
    if "destination" not in action.parameters:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_PAYMENT_DESTINATION_REQUIRED",
                message="EXECUTE_PAYMENT requires a destination parameter",
            )
        )
    if action.evidence_sha256 is None:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_AUTHORITATIVE_EVIDENCE_REQUIRED",
                message="EXECUTE_PAYMENT requires authoritative evidence",
            )
        )
    return blockers


def _check_deploy_software(action: ProposedAction) -> list[AuthorizationBlocker]:
    blockers: list[AuthorizationBlocker] = []
    if "revision" not in action.parameters:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_DEPLOY_REVISION_REQUIRED",
                message="DEPLOY_SOFTWARE requires a revision identifier",
            )
        )
    if "environment" not in action.parameters:
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_DEPLOY_ENVIRONMENT_REQUIRED",
                message="DEPLOY_SOFTWARE requires an environment",
            )
        )
    elif (
        action.parameters["environment"] == "production"
        and "human_approved_production" not in action.parameters
    ):
        blockers.append(
            AuthorizationBlocker(
                code="ACTION_DEPLOY_PRODUCTION_APPROVAL_REQUIRED",
                message="Production deploy requires an explicit approval marker",
            )
        )
    return blockers


def _check_generic_requires_target(action: ProposedAction) -> list[AuthorizationBlocker]:
    if action.target.strip():
        return []
    return [AuthorizationBlocker(code="ACTION_TARGET_REQUIRED", message="Target is required")]


REQUIREMENT_CHECKS: Mapping[
    ActionType, Callable[[ProposedAction], list[AuthorizationBlocker]]
] = MappingProxyType(
    {
        ActionType.SIGN_DOCUMENT: _check_sign_document,
        ActionType.EXECUTE_PAYMENT: _check_execute_payment,
        ActionType.DEPLOY_SOFTWARE: _check_deploy_software,
        ActionType.SEND_EMAIL: _check_generic_requires_target,
        ActionType.EXECUTE_PURCHASE: _check_generic_requires_target,
        ActionType.DATABASE_WRITE: _check_generic_requires_target,
    }
)


def authorize_action(action: ProposedAction) -> AuthorizationDecision:
    """Deterministic, action-type-specific authorization.

    For SIGN_DOCUMENT this is a structural invariant check (the required artifact,
    evidence, and policy-profile hashes are present). The real gating for
    SIGN_DOCUMENT — evidence sufficiency, critical-claim checks, blocked/ready state
    — continues to be decided entirely by the unchanged Phase 1 baseline
    (DeterministicPolicyEngine) plus PolicyProfileEvaluator plus ApprovalSendService.
    """

    blockers = REQUIREMENT_CHECKS[action.action_type](action)
    outcome = PolicyOutcome.BLOCKED if blockers else PolicyOutcome.READY_FOR_APPROVAL
    return AuthorizationDecision(
        action_id=action.action_id,
        action_type=action.action_type,
        action_sha256=action_sha256(action),
        outcome=outcome,
        blockers=tuple(blockers),
        requires_human_approval=True,
        execution_capability=get_capability(action.action_type),
    )
