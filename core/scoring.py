"""
Scoring rules for contention resolution.

Architecture (Open/Closed Principle):
  - ScoringRule is an abstract base class.
  - Each objective is a separate concrete rule.
  - Adding a new rule = adding a new class, zero changes to the scheduler.
  - The scheduler accepts a list of (rule, weight) pairs — fully data-driven.

Rules return a PENALTY for a given bus being made to wait.
Higher penalty = that bus should NOT wait = it should go first.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List


class ScoringRule(ABC):
    """Abstract base for all soft scoring rules."""

    @abstractmethod
    def penalty(
        self,
        bus_id: str,
        operator: str,
        current_wait_min: float,
        operator_fleet_waits: Dict[str, List[float]],
        all_bus_waits: Dict[str, float],
    ) -> float:
        """
        Return the penalty score for making this bus wait one more slot.
        Higher = worse = this bus should go first.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str: ...


class IndividualWaitRule(ScoringRule):
    """
    Penalise adding more wait to a bus that has already waited a lot.
    Prevents starvation of any individual bus.
    """

    @property
    def name(self) -> str:
        return "individual"

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        return current_wait_min


class OperatorFairnessRule(ScoringRule):
    """
    Penalise adding wait to a bus whose operator's fleet average wait is already high.
    Keeps operators on equal footing.
    """

    @property
    def name(self) -> str:
        return "operator"

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        fleet_waits = operator_fleet_waits.get(operator, [])
        if not fleet_waits:
            return 0.0
        return sum(fleet_waits) / len(fleet_waits)


class OverallSystemRule(ScoringRule):
    """
    Penalise adding wait to a bus that contributes most to total system delay.
    Minimises aggregate delay across the whole network.
    """

    @property
    def name(self) -> str:
        return "overall"

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        if not all_bus_waits:
            return 0.0
        total = sum(all_bus_waits.values())
        # Marginal cost: how much does this bus's wait contribute as a fraction of total
        avg = total / len(all_bus_waits)
        return avg


class PriorityRule(ScoringRule):
    """
    Future rule: explicit bus priority (express services, etc.).
    Plug in by adding to the rules list — no scheduler changes needed.
    """

    @property
    def name(self) -> str:
        return "priority"

    def __init__(self, priorities: Dict[str, int]):
        self._priorities = priorities  # bus_id → priority level

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        return float(self._priorities.get(bus_id, 0)) * 10.0


class WeightedScorer:
    """
    Combines multiple ScoringRules with weights into a single penalty score.
    The weights come from ScenarioConfig.weights — one obvious place to change them.
    """

    def __init__(self, rules_with_weights: List[tuple[ScoringRule, float]]):
        self._rules = rules_with_weights

    def score(
        self,
        bus_id: str,
        operator: str,
        current_wait_min: float,
        operator_fleet_waits: Dict[str, List[float]],
        all_bus_waits: Dict[str, float],
    ) -> float:
        total = 0.0
        for rule, weight in self._rules:
            total += weight * rule.penalty(
                bus_id, operator, current_wait_min,
                operator_fleet_waits, all_bus_waits
            )
        return total

    @classmethod
    def from_weights(cls, weights) -> "WeightedScorer":
        """
        Factory: build the standard three-rule scorer from a Weights object.
        To change a weight: edit the scenario JSON. That's it.
        """
        return cls([
            (IndividualWaitRule(), weights.individual),
            (OperatorFairnessRule(), weights.operator),
            (OverallSystemRule(), weights.overall),
        ])
