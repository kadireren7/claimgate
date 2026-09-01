"""Productized red-team validation using existing ClaimGate boundaries."""

from claimgate.redteam.models import (
    AttackOutcome,
    AttackResult,
    AttackScenario,
    AttackScenarioId,
    SecurityAssertion,
)
from claimgate.redteam.runner import AttackRunner
from claimgate.redteam.scenarios import ATTACK_SCENARIOS, PROMPT_INJECTION_TEXT

__all__ = [
    "ATTACK_SCENARIOS",
    "PROMPT_INJECTION_TEXT",
    "AttackOutcome",
    "AttackResult",
    "AttackRunner",
    "AttackScenario",
    "AttackScenarioId",
    "SecurityAssertion",
]
