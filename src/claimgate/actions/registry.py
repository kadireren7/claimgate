"""Static, backend-only registry of what ClaimGate can execute.

There is no function to add, remove, or mutate an entry: browser requests and
semantic providers cannot register a new capability because no such API exists
anywhere in this module or package.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from claimgate.actions.models import ActionType, ExecutionCapability

CAPABILITY_REGISTRY: Mapping[ActionType, ExecutionCapability] = MappingProxyType(
    {
        ActionType.SIGN_DOCUMENT: ExecutionCapability(
            action_type=ActionType.SIGN_DOCUMENT,
            supported=True,
            live_execution=True,
            adapter="FOXIT_ESIGN",
        ),
        ActionType.SEND_EMAIL: ExecutionCapability(
            action_type=ActionType.SEND_EMAIL,
            supported=True,
            live_execution=False,
            adapter="SIMULATED",
        ),
        ActionType.DEPLOY_SOFTWARE: ExecutionCapability(
            action_type=ActionType.DEPLOY_SOFTWARE,
            supported=True,
            live_execution=False,
            adapter="SIMULATED",
        ),
        ActionType.EXECUTE_PURCHASE: ExecutionCapability(
            action_type=ActionType.EXECUTE_PURCHASE,
            supported=True,
            live_execution=False,
            adapter="SIMULATED",
        ),
        ActionType.EXECUTE_PAYMENT: ExecutionCapability(
            action_type=ActionType.EXECUTE_PAYMENT,
            supported=True,
            live_execution=False,
            adapter="SIMULATED",
        ),
        ActionType.DATABASE_WRITE: ExecutionCapability(
            action_type=ActionType.DATABASE_WRITE,
            supported=True,
            live_execution=False,
            adapter="SIMULATED",
        ),
    }
)


def get_capability(action_type: ActionType) -> ExecutionCapability:
    return CAPABILITY_REGISTRY[action_type]
