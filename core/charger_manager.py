"""
ChargerManager: tracks the availability of chargers at a single station.

Supports num_chargers >= 1.
Returns the earliest slot a new bus can start charging.

Single Responsibility: charger slot management only.
"""

from __future__ import annotations
import heapq
from typing import List


class ChargerManager:
    """
    Manages a fixed number of chargers at one station.
    Internally uses a min-heap of "next available time" for each charger.

    Usage:
        mgr = ChargerManager(num_chargers=2)
        start = mgr.next_available_after(arrival_time=100.0)
        mgr.book(start, duration=25.0)
    """

    def __init__(self, num_chargers: int):
        if num_chargers < 1:
            raise ValueError("A station must have at least 1 charger.")
        # heap contains "time when each charger becomes free"
        self._free_at: List[float] = [0.0] * num_chargers
        heapq.heapify(self._free_at)

    def next_available_after(self, arrival_min: float) -> float:
        """
        Return the earliest start time for a bus arriving at arrival_min.
        If the soonest-free charger is free before or at arrival, bus starts immediately.
        """
        soonest_free = self._free_at[0]   # min-heap peek
        return max(soonest_free, arrival_min)

    def book(self, start_min: float, duration_min: float) -> float:
        """
        Reserve the next available charger starting at start_min for duration_min.
        Returns the charge_end time.
        """
        soonest_free = heapq.heappop(self._free_at)
        charge_end = start_min + duration_min
        heapq.heappush(self._free_at, charge_end)
        return charge_end

    def reset(self) -> None:
        """Reset all chargers to free (used for re-simulation passes)."""
        n = len(self._free_at)
        self._free_at = [0.0] * n
        heapq.heapify(self._free_at)
