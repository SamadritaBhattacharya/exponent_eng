"""
ScheduleValidator: POST-phase hard constraint verification.

Checks every hard rule after the scheduler produces a result.
Returns a list of violations (empty = valid schedule).

Single Responsibility: validation only.
Open/Closed: new hard rule = new _check_* method.
"""

from __future__ import annotations
from typing import List
from core.models import ScheduleResult, BusTimeline, StationQueue


class ValidationError:
    def __init__(self, bus_id: str, rule: str, message: str):
        self.bus_id = bus_id
        self.rule = rule
        self.message = message

    def __str__(self) -> str:
        return f"[{self.rule}] {self.bus_id}: {self.message}"


class ScheduleValidator:
    """Validates a ScheduleResult against all hard constraints."""

    def validate(self, result: ScheduleResult) -> List[ValidationError]:
        errors: List[ValidationError] = []
        errors.extend(self._check_range_compliance(result))
        errors.extend(self._check_no_charger_overlap(result))
        errors.extend(self._check_station_order(result))
        errors.extend(self._check_timeline_continuity(result))
        errors.extend(self._check_all_buses_complete(result))
        return errors

    # ─────────────────────────── checks ───────────────────────────────────────

    def _check_range_compliance(self, result: ScheduleResult) -> List[ValidationError]:
        errors = []
        config = result.scenario
        route = config.route
        battery = config.default_battery_range_km

        for bus_id, tl in result.bus_timelines.items():
            bus = tl.bus
            actual_range = bus.battery_range_km

            # Build leg list: origin → stations → destination
            from_stops = [self._origin(tl, route)]
            for e in tl.charge_events:
                from_stops.append(e.station_id)

            to_stops = list(from_stops[1:]) + [self._destination(tl, route)]

            for frm, to in zip(from_stops, to_stops):
                d1 = route.cumulative_distance_from_origin(frm, bus.direction)
                d2 = route.cumulative_distance_from_origin(to, bus.direction)
                leg = abs(d2 - d1)
                if leg > actual_range + 0.01:   # float tolerance
                    errors.append(ValidationError(
                        bus_id, "RANGE",
                        f"Leg {frm}→{to} is {leg:.1f} km, exceeds range {actual_range} km"
                    ))
        return errors

    def _check_no_charger_overlap(self, result: ScheduleResult) -> List[ValidationError]:
        errors = []
        for station_id, queue in result.station_queues.items():
            station = queue.station
            # Group events by charger slot (sorted by charge_start)
            sorted_events = sorted(queue.events, key=lambda e: e.charge_start_min)
            for i in range(len(sorted_events) - 1):
                a = sorted_events[i]
                b = sorted_events[i + 1]
                if b.charge_start_min < a.charge_end_min - 0.01:
                    errors.append(ValidationError(
                        b.bus_id, "CHARGER_OVERLAP",
                        f"Station {station_id}: {a.bus_id} ends at {a.charge_end_min:.1f}, "
                        f"{b.bus_id} starts at {b.charge_start_min:.1f}"
                    ))
        return errors

    def _check_station_order(self, result: ScheduleResult) -> List[ValidationError]:
        errors = []
        config = result.scenario
        for bus_id, tl in result.bus_timelines.items():
            bus = tl.bus
            stations_in_order = [s.id for s in config.route.stations_in_direction(bus.direction)]
            visited = [e.station_id for e in tl.charge_events]
            indices = [stations_in_order.index(s) for s in visited if s in stations_in_order]
            if indices != sorted(indices):
                errors.append(ValidationError(
                    bus_id, "STATION_ORDER",
                    f"Visited stations {visited} are not in route order"
                ))
        return errors

    def _check_timeline_continuity(self, result: ScheduleResult) -> List[ValidationError]:
        errors = []
        for bus_id, tl in result.bus_timelines.items():
            prev_end = tl.bus.departure_min
            for event in tl.charge_events:
                if event.arrival_min < prev_end - 0.01:
                    errors.append(ValidationError(
                        bus_id, "TIMELINE",
                        f"Arrival at {event.station_id} ({event.arrival_min:.1f}) "
                        f"is before previous event end ({prev_end:.1f})"
                    ))
                if event.charge_start_min < event.arrival_min - 0.01:
                    errors.append(ValidationError(
                        bus_id, "TIMELINE",
                        f"Charge starts ({event.charge_start_min:.1f}) before arrival ({event.arrival_min:.1f})"
                    ))
                if event.charge_end_min < event.charge_start_min:
                    errors.append(ValidationError(
                        bus_id, "TIMELINE",
                        f"Charge ends before it starts at {event.station_id}"
                    ))
                prev_end = event.charge_end_min
        return errors

    def _check_all_buses_complete(self, result: ScheduleResult) -> List[ValidationError]:
        errors = []
        for bus_id, tl in result.bus_timelines.items():
            if tl.final_arrival_min <= 0:
                errors.append(ValidationError(bus_id, "COMPLETION", "Bus has no final arrival time"))
            if not tl.charge_events:
                errors.append(ValidationError(bus_id, "COMPLETION", "Bus has no charge events (trip infeasible)"))
        return errors

    # ─────────────────────────── helpers ──────────────────────────────────────

    @staticmethod
    def _origin(tl: BusTimeline, route) -> str:
        from core.models import Direction
        o, d = route.terminals
        return o if tl.bus.direction == Direction.BK else d

    @staticmethod
    def _destination(tl: BusTimeline, route) -> str:
        from core.models import Direction
        o, d = route.terminals
        return d if tl.bus.direction == Direction.BK else o
