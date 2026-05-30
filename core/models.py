"""
Domain models for the Bus Charging Scheduler.

Design principles:
- Immutable value objects where possible (dataclasses with frozen=True)
- Rich domain objects that carry behaviour, not just data
- All physical constants live in the scenario config, never hardcoded here
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict
from enum import Enum


class Direction(str, Enum):
    BK = "BK"   # Bengaluru → Kochi
    KB = "KB"   # Kochi → Bengaluru


@dataclass(frozen=True)
class Segment:
    """One road segment between two named stops."""
    from_stop: str
    to_stop: str
    distance_km: float


@dataclass(frozen=True)
class Station:
    """
    A charging-capable stop along the route.
    num_chargers > 1 is already supported in the model —
    the scheduler will use a list of charger slots.
    """
    id: str
    name: str
    num_chargers: int = 1
    charge_time_min: float = 25.0   # per-station override supported


@dataclass(frozen=True)
class Route:
    """
    An ordered sequence of segments defining a one-way trip.
    Terminals (first and last stop) are NOT scheduling stations —
    they are full-charge endpoints.
    """
    id: str
    segments: List[Segment]
    charging_stations: List[Station]   # ordered along BK direction
    speed_kmh: float = 60.0

    @property
    def stops(self) -> List[str]:
        """All stop names in BK order including terminals."""
        if not self.segments:
            return []
        return [self.segments[0].from_stop] + [s.to_stop for s in self.segments]

    @property
    def terminals(self) -> tuple[str, str]:
        return self.stops[0], self.stops[-1]

    def cumulative_distance_from_origin(self, stop: str, direction: Direction) -> float:
        """Distance from the origin terminal to a given stop, respecting direction."""
        stops = self.stops if direction == Direction.BK else list(reversed(self.stops))
        segments_ordered = self.segments if direction == Direction.BK else list(reversed(self.segments))
        dist = 0.0
        for i, s in enumerate(stops):
            if s == stop:
                return dist
            dist += segments_ordered[i].distance_km
        raise ValueError(f"Stop '{stop}' not found in route '{self.id}'")

    def travel_time_min(self, from_stop: str, to_stop: str, direction: Direction) -> float:
        """Minutes to travel between two consecutive stops (no intermediate stops)."""
        d1 = self.cumulative_distance_from_origin(from_stop, direction)
        d2 = self.cumulative_distance_from_origin(to_stop, direction)
        return abs(d2 - d1) / self.speed_kmh * 60.0

    def stations_in_direction(self, direction: Direction) -> List[Station]:
        """Charging stations ordered as encountered for this direction."""
        if direction == Direction.BK:
            return list(self.charging_stations)
        return list(reversed(self.charging_stations))

    def total_distance_km(self) -> float:
        return sum(s.distance_km for s in self.segments)


@dataclass(frozen=True)
class Bus:
    """
    A single bus on a single trip.
    battery_range_km: per-bus override for future heterogeneous fleets.
    priority: higher = more urgent (e.g. premium/express service).
    """
    id: str
    operator: str
    direction: Direction
    departure_min: float        # minutes from epoch (00:00 day 1)
    route_id: str
    battery_range_km: float = 240.0
    priority: int = 0           # 0 = normal, higher = more urgent


@dataclass
class ChargeEvent:
    """One charge stop for a bus at a specific station."""
    bus_id: str
    station_id: str
    arrival_min: float
    wait_min: float
    charge_start_min: float
    charge_end_min: float

    @property
    def departure_min(self) -> float:
        return self.charge_end_min


@dataclass
class BusTimeline:
    """Complete computed schedule for one bus."""
    bus: Bus
    charging_plan: List[str]        # station IDs in visit order
    charge_events: List[ChargeEvent]
    final_arrival_min: float

    @property
    def total_wait_min(self) -> float:
        return sum(e.wait_min for e in self.charge_events)

    @property
    def total_charge_min(self) -> float:
        return sum(e.charge_end_min - e.charge_start_min for e in self.charge_events)

    @property
    def total_trip_min(self) -> float:
        return self.final_arrival_min - self.bus.departure_min

    @property
    def pure_drive_min(self) -> float:
        return self.total_trip_min - self.total_wait_min - self.total_charge_min


@dataclass
class StationQueue:
    """All charge events at a station, in scheduled order."""
    station: Station
    events: List[ChargeEvent] = field(default_factory=list)

    def add_event(self, event: ChargeEvent) -> None:
        self.events.append(event)
        self.events.sort(key=lambda e: e.charge_start_min)

    @property
    def peak_queue_length(self) -> int:
        """Max number of buses queued (waiting) at the same instant."""
        if not self.events:
            return 0
        peak = 0
        for e in self.events:
            waiting_at_arrival = sum(
                1 for other in self.events
                if other.arrival_min <= e.arrival_min < other.charge_start_min
            )
            peak = max(peak, waiting_at_arrival)
        return peak

    @property
    def utilisation_pct(self) -> float:
        if not self.events:
            return 0.0
        first = self.events[0].charge_start_min
        last = self.events[-1].charge_end_min
        span = last - first
        if span == 0:
            return 100.0
        busy = sum(e.charge_end_min - e.charge_start_min for e in self.events)
        return round(busy / span * 100, 1)


@dataclass(frozen=True)
class Weights:
    """
    Tunable objective weights for the scheduler.
    Each weight is a non-negative float.
    Changing a scenario's weights is a one-line data change.
    """
    individual: float = 1.0   # penalise long waits for a single bus
    operator: float = 1.0     # penalise uneven fleet-level delays
    overall: float = 1.0      # penalise high total system delay


@dataclass
class ScenarioConfig:
    """
    Everything the scheduler needs for one scenario.
    This is the single source of truth loaded from a JSON data file.
    """
    id: str
    name: str
    description: str
    route: Route
    buses: List[Bus]
    weights: Weights
    default_battery_range_km: float = 240.0
    default_charge_time_min: float = 25.0
    default_speed_kmh: float = 60.0


@dataclass
class ScheduleResult:
    """Full output produced by the scheduler for one scenario."""
    scenario: ScenarioConfig
    bus_timelines: Dict[str, BusTimeline]   # bus_id → timeline
    station_queues: Dict[str, StationQueue]  # station_id → queue

    def operator_stats(self) -> Dict[str, Dict]:
        """Aggregate stats per operator."""
        stats: Dict[str, Dict] = {}
        for tl in self.bus_timelines.values():
            op = tl.bus.operator
            if op not in stats:
                stats[op] = {"count": 0, "total_wait": 0.0, "max_wait": 0.0, "total_trip": 0.0}
            stats[op]["count"] += 1
            stats[op]["total_wait"] += tl.total_wait_min
            stats[op]["max_wait"] = max(stats[op]["max_wait"], tl.total_wait_min)
            stats[op]["total_trip"] += tl.total_trip_min
        for op in stats:
            c = stats[op]["count"]
            stats[op]["avg_wait"] = round(stats[op]["total_wait"] / c, 1)
            stats[op]["avg_trip"] = round(stats[op]["total_trip"] / c, 1)
        return stats

    def system_stats(self) -> Dict:
        timelines = list(self.bus_timelines.values())
        if not timelines:
            return {}
        return {
            "total_buses": len(timelines),
            "total_wait_min": round(sum(t.total_wait_min for t in timelines), 1),
            "max_single_wait_min": round(max(t.total_wait_min for t in timelines), 1),
            "avg_trip_min": round(sum(t.total_trip_min for t in timelines) / len(timelines), 1),
        }
