"""Backend-only execution adapters.

SIGN_DOCUMENT is the only ActionType with a real external execution adapter
(FoxitSignDocumentExecutor, a thin wrapper over the existing, unmodified
ESignSender protocol). Every other ActionType is executed only through
SimulatedActionExecutor: deterministic, in-process, no network call, no real
side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Protocol

from claimgate.actions.models import ActionType, ProposedAction
from claimgate.actions.registry import get_capability

if TYPE_CHECKING:
    from claimgate.application.approval import ESignSender
    from claimgate.integrations.foxit_esign import Signer


class ActionExecutionError(RuntimeError):
    """Raised when an action is executed through the wrong or an unauthorized adapter."""


@dataclass(frozen=True)
class ActionExecutionResult:
    action_id: str
    action_type: ActionType
    status: Literal["EXECUTED", "SIMULATED"]
    detail: str
    external_identifier: str | None = None


class ActionExecutor(Protocol):
    def execute(self, action: ProposedAction) -> ActionExecutionResult: ...


class SimulatedActionExecutor:
    """Backend-only, deterministic, no network, no real side effect.

    The executor for every ActionType except SIGN_DOCUMENT.
    """

    def __init__(self) -> None:
        self.calls: list[ProposedAction] = []

    def execute(self, action: ProposedAction) -> ActionExecutionResult:
        capability = get_capability(action.action_type)
        if capability.live_execution:
            raise ActionExecutionError(
                f"{action.action_type.value} has live execution and must not use "
                "SimulatedActionExecutor"
            )
        self.calls.append(action)
        return ActionExecutionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            status="SIMULATED",
            detail=f"SIMULATION ONLY — no external {action.action_type.value} execution occurred",
        )


class FoxitSignDocumentExecutor:
    """Thin adapter over the existing, unmodified ESignSender protocol.

    The sole live executor in the system; only constructible and callable for
    SIGN_DOCUMENT.
    """

    def __init__(self, sender: ESignSender, *, pdf_path: Path, signer: Signer) -> None:
        self._sender = sender
        self._pdf_path = pdf_path
        self._signer = signer

    def execute(self, action: ProposedAction) -> ActionExecutionResult:
        if action.action_type is not ActionType.SIGN_DOCUMENT:
            raise ActionExecutionError("FoxitSignDocumentExecutor only executes SIGN_DOCUMENT")
        if not get_capability(action.action_type).live_execution:
            raise ActionExecutionError(
                "SIGN_DOCUMENT capability is not marked for live execution"
            )
        result = self._sender.send_pdf_for_signature(self._pdf_path, self._signer)
        return ActionExecutionResult(
            action_id=action.action_id,
            action_type=action.action_type,
            status="EXECUTED",
            detail="Foxit eSign send completed",
            external_identifier=result.folder_id,
        )


def get_executor(action_type: ActionType, **live_kwargs: Any) -> ActionExecutor:
    """The only factory.

    SIGN_DOCUMENT requires ``sender``/``pdf_path``/``signer`` keyword arguments and
    returns FoxitSignDocumentExecutor; every other action type ignores keyword
    arguments and returns a fresh SimulatedActionExecutor. There is no override
    parameter: callers cannot request a live executor for a simulated-only type.
    """

    if action_type is ActionType.SIGN_DOCUMENT:
        return FoxitSignDocumentExecutor(**live_kwargs)
    return SimulatedActionExecutor()
