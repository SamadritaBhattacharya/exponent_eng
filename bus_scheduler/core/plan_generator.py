"""
ChargingPlanGenerator: Given a route, direction, and battery range,
enumerate every valid subset of stations a bus can use.

Single Responsibility: only plan enumeration, no scheduling logic.
Open/Closed: new constraints (e.g. mandatory stop) → new validator, no changes here.
"""

from __future__ import annotations
from itertools import combinations
from typing import List, Tuple
from core.models import Route, Direction, Station


class ChargingPlanGenerator:
    """
    Enumerates valid charging plans for a given direction and battery range.

    A plan is a list of station IDs in the order they will be visited.
    A plan is valid if every leg (origin→s1, s1→s2, …, sN→dest) ≤ battery_range_km.

    Plans are returned sorted: fewest stops first, then by total leg balance
    (prefer plans with more evenly distributed legs — greater minimum slack).
    """

    def __init__(self, route: Route, battery_range_km: float):
        self._route = route
        self._battery_range = battery_range_km

    def valid_plans(self, direction: Direction) -> List[List[str]]:
        """Return all valid charging plans for this direction, ranked best-first."""
        stations = self._route.stations_in_direction(direction)
        origin, destination = self._directional_terminals(direction)

        valid: List[Tuple[List[str], float, int]] = []  # (plan, min_slack, num_stops)

        for size in range(1, len(stations) + 1):
            for combo in combinations(stations, size):
                plan = [s.id for s in combo]
                legs = self._legs(plan, origin, destination, direction)
                if all(leg <= self._battery_range for leg in legs):
                    min_slack = min(self._battery_range - leg for leg in legs)
                    valid.append((plan, min_slack, size))

        # Sort: fewer stops first; within same stop count, more slack first
        valid.sort(key=lambda x: (x[2], -x[1]))
        return [plan for plan, _, _ in valid]

    def is_valid_plan(self, plan: List[str], direction: Direction) -> bool:
        """Validate a specific plan without enumerating all options."""
        origin, destination = self._directional_terminals(direction)
        legs = self._legs(plan, origin, destination, direction)
        return all(0 < leg <= self._battery_range for leg in legs)

    def minimum_stops_required(self, direction: Direction) -> int:
        """
        Theoretical minimum charges needed to complete the trip.
        ceil(total_distance / range) - 1 charges = ceil(540/240) - 1 = 2
        """
        import math
        total = self._route.total_distance_km()
        return math.ceil(total / self._battery_range) - 1

    # ------------------------------------------------------------------ private

    def _directional_terminals(self, direction: Direction) -> Tuple[str, str]:
        origin_stop, dest_stop = self._route.terminals
        if direction == Direction.BK:
            return origin_stop, dest_stop
        return dest_stop, origin_stop

    def _legs(
        self,
        plan: List[str],
        origin: str,
        destination: str,
        direction: Direction,
    ) -> List[float]:
        """Compute the distance of every leg in this plan."""
        stops = [origin] + plan + [destination]
        legs = []
        for i in range(len(stops) - 1):
            d = self._route.cumulative_distance_from_origin(stops[i + 1], direction) \
              - self._route.cumulative_distance_from_origin(stops[i], direction)
            legs.append(abs(d))
        return legs
