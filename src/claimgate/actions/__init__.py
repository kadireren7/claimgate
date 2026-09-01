"""Vendor-neutral authorization layer for irreversible AI-agent actions.

SIGN_DOCUMENT is the first concrete ActionType and the only one with a real
external execution adapter in this phase; every other ActionType
(SEND_EMAIL, DEPLOY_SOFTWARE, EXECUTE_PURCHASE, EXECUTE_PAYMENT,
DATABASE_WRITE) is simulated/demo-only.
"""

from claimgate.actions.adapters import (
    ActionExecutionError,
    ActionExecutionResult,
    ActionExecutor,
    FoxitSignDocumentExecutor,
    SimulatedActionExecutor,
    get_executor,
)
from claimgate.actions.authorization import (
    REQUIREMENT_CHECKS,
    action_sha256,
    authorize_action,
    canonical_action_json,
)
from claimgate.actions.models import (
    ACTION_RISK_BY_TYPE,
    ActionApprovalRecord,
    ActionBinding,
    ActionParameterValue,
    ActionRisk,
    ActionType,
    AuthorizationBlocker,
    AuthorizationDecision,
    ExecutionCapability,
    ProposedAction,
    create_proposed_action,
    is_approval_valid,
)
from claimgate.actions.registry import CAPABILITY_REGISTRY, get_capability

__all__ = [
    "ACTION_RISK_BY_TYPE",
    "CAPABILITY_REGISTRY",
    "REQUIREMENT_CHECKS",
    "ActionApprovalRecord",
    "ActionBinding",
    "ActionExecutionError",
    "ActionExecutionResult",
    "ActionExecutor",
    "ActionParameterValue",
    "ActionRisk",
    "ActionType",
    "AuthorizationBlocker",
    "AuthorizationDecision",
    "ExecutionCapability",
    "FoxitSignDocumentExecutor",
    "ProposedAction",
    "SimulatedActionExecutor",
    "action_sha256",
    "authorize_action",
    "canonical_action_json",
    "create_proposed_action",
    "get_capability",
    "get_executor",
    "is_approval_valid",
]
