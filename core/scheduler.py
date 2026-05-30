"""
Scheduler: event-driven simulation with weighted contention resolution.

Algorithm:
  1. Assign each bus its best charging plan (fewest stops, most range slack).
  2. Simulate forward in time using a global min-heap of events:
       - ARRIVAL  event: bus reaches a station, joins its waiting queue
       - DISPATCH event: the station charger just freed; pick the highest-scoring waiter
  3. WeightedScorer re-scores all waiters at every DISPATCH event to implement
     weighted priority (not FCFS).
  4. After simulation, buses with excessive total_wait try an alternative plan
     that avoids their most-congested station.
  5. Repeat until stable or max_iterations reached.

SOLID:
  SRP — scoring, plan generation, charger tracking each in their own class.
  OCP — new rule → new ScoringRule subclass, zero changes here.
  DIP — Scheduler depends on WeightedScorer / ChargingPlanGenerator interfaces.
"""

from __future__ import annotations
import heapq
from collections import defaultdict
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass, field

from core.models import (
    Bus, Direction, Route, ScenarioConfig,
    ChargeEvent, BusTimeline, StationQueue, ScheduleResult,
)
from core.plan_generator import ChargingPlanGenerator
from core.scoring import WeightedScorer


# ─────────────────────────── internal state ──────────────────────────────────

@dataclass
class _BusState:
    bus: Bus
    plan: List[str]
    plan_index: int = 0
    current_time: float = 0.0
    total_wait: float = 0.0
    events: List[ChargeEvent] = field(default_factory=list)

    @property
    def next_station(self) -> Optional[str]:
        if self.plan_index < len(self.plan):
            return self.plan[self.plan_index]
        return None


class _EvType(int, Enum):
    ARRIVAL  = 0   # bus arrives at station (sorts before DISPATCH at same time)
    DISPATCH = 1   # charger freed; pick next waiter


@dataclass(order=True)
class _Event:
    """
    Min-heap entry.  Ordered by (time, ev_type, bus_id) for determinism.
    ARRIVAL sorts before DISPATCH at the same time so all arrivals are
    registered before we pick who goes next.
    """
    time:     float
    ev_type:  _EvType    # 0=ARRIVAL sorts first
    bus_id:   str        # "" for DISPATCH events
    station_id: str = field(compare=False)


@dataclass
class _Waiter:
    bus_id: str
    arrival_min: float


# ─────────────────────────────── scheduler ────────────────────────────────────

class Scheduler:
    """
    Produces a ScheduleResult from a ScenarioConfig.

    reassignment_threshold_min: If a bus's total wait exceeds this,
        try switching it to a plan that avoids its most-congested station.
    max_iterations: Safety cap on plan-reassignment rounds.
    """

    def __init__(
        self,
        reassignment_threshold_min: float = 30.0,
        max_iterations: int = 10,
    ):
        self._threshold = reassignment_threshold_min
        self._max_iter = max_iterations

    def run(self, config: ScenarioConfig) -> ScheduleResult:
        scorer = WeightedScorer.from_weights(config.weights)
        generator = ChargingPlanGenerator(config.route, config.default_battery_range_km)

        valid_plans: Dict[Direction, List[List[str]]] = {
            Direction.BK: generator.valid_plans(Direction.BK),
            Direction.KB: generator.valid_plans(Direction.KB),
        }
        if not valid_plans[Direction.BK] or not valid_plans[Direction.KB]:
            raise ValueError("No valid charging plan exists for this route/range combination.")

        bus_states: Dict[str, _BusState] = {
            bus.id: _BusState(
                bus=bus,
                plan=valid_plans[bus.direction][0],
                current_time=bus.departure_min,
            )
            for bus in config.buses
        }

        last_events:   Dict[str, list]  = {}
        last_arrivals: Dict[str, float] = {}
        plans_tried:   Dict[str, set]   = {b.id: set() for b in config.buses}

        for _ in range(self._max_iter):
            sim = self._simulate(bus_states, config, scorer)

            for bus_id, state in bus_states.items():
                last_events[bus_id] = list(state.events)
            last_arrivals = dict(sim)

            if not self._try_reassign(bus_states, config, valid_plans, plans_tried):
                break

            for state in bus_states.values():
                state.plan_index  = 0
                state.current_time = state.bus.departure_min
                state.total_wait  = 0.0
                state.events      = []

        for bus_id, state in bus_states.items():
            state.events = last_events.get(bus_id, [])

        return self._build_result(config, bus_states, last_arrivals)

    # ─────────────────────────── core simulation ──────────────────────────────

    def _simulate(
        self,
        bus_states: Dict[str, _BusState],
        config: ScenarioConfig,
        scorer: WeightedScorer,
    ) -> Dict[str, float]:
        """
        Full forward simulation. Returns {bus_id: final_arrival_min}.

        Two event types on the same heap:
          ARRIVAL  — bus just drove in; joins the station's waiting list.
          DISPATCH — charger just freed; pick the highest-scoring waiter,
                     commit its charge slot, and push its next event.

        This guarantees every waiter is eventually served even when no new
        arrivals come to re-trigger dispatching.
        """
        for state in bus_states.values():
            state.plan_index   = 0
            state.current_time = state.bus.departure_min
            state.total_wait   = 0.0
            state.events       = []

        # Per-station: list of waiting buses
        waiting: Dict[str, List[_Waiter]] = defaultdict(list)
        # Per-station: when each charger slot is next free (min-heap per station)
        charger_free: Dict[str, List[float]] = {
            s.id: [0.0] * s.num_chargers
            for s in config.route.charging_stations
        }
        for heap in charger_free.values():
            heapq.heapify(heap)

        station_charge_time: Dict[str, float] = {
            s.id: s.charge_time_min for s in config.route.charging_stations
        }

        # Seed: each bus heads to its first station
        global_heap: List[_Event] = []
        for bus_id, state in bus_states.items():
            if state.next_station:
                t = self._eta(state, state.next_station, config)
                heapq.heappush(global_heap, _Event(
                    time=t, ev_type=_EvType.ARRIVAL,
                    bus_id=bus_id, station_id=state.next_station,
                ))

        final_arrivals: Dict[str, float] = {}

        while global_heap:
            ev = heapq.heappop(global_heap)
            sid = ev.station_id

            if ev.ev_type == _EvType.ARRIVAL:
                # Record that this bus is now waiting at the station
                bus_states[ev.bus_id].current_time = ev.time
                waiting[sid].append(_Waiter(bus_id=ev.bus_id, arrival_min=ev.time))
                # If charger is already free, immediately trigger a dispatch
                if charger_free[sid][0] <= ev.time:
                    heapq.heappush(global_heap, _Event(
                        time=ev.time, ev_type=_EvType.DISPATCH,
                        bus_id="", station_id=sid,
                    ))

            else:  # DISPATCH
                waiters = waiting[sid]
                if not waiters:
                    continue

                # Re-score all waiters; pick the most urgent one
                chosen = self._pick_best(waiters, sid, bus_states, scorer)
                waiters.remove(chosen)

                # Book the soonest-free charger slot
                soonest = heapq.heappop(charger_free[sid])
                charge_start = max(soonest, chosen.arrival_min)
                charge_dur   = station_charge_time[sid]
                charge_end   = charge_start + charge_dur
                heapq.heappush(charger_free[sid], charge_end)

                wait = charge_start - chosen.arrival_min

                # Commit the charge event
                ce = ChargeEvent(
                    bus_id=chosen.bus_id,
                    station_id=sid,
                    arrival_min=chosen.arrival_min,
                    wait_min=wait,
                    charge_start_min=charge_start,
                    charge_end_min=charge_end,
                )
                state = bus_states[chosen.bus_id]
                state.events.append(ce)
                state.total_wait   += wait
                state.current_time  = charge_end
                state.plan_index   += 1

                # Push next event for this bus
                if state.next_station:
                    t = self._eta(state, state.next_station, config)
                    heapq.heappush(global_heap, _Event(
                        time=t, ev_type=_EvType.ARRIVAL,
                        bus_id=chosen.bus_id, station_id=state.next_station,
                    ))
                else:
                    dest      = self._dest(state.bus, config.route)
                    last_stop = state.events[-1].station_id
                    d = abs(
                        config.route.cumulative_distance_from_origin(dest, state.bus.direction)
                        - config.route.cumulative_distance_from_origin(last_stop, state.bus.direction)
                    )
                    final_arrivals[chosen.bus_id] = charge_end + d / config.route.speed_kmh * 60.0

                # If more buses are waiting and charger frees before any of them arrive,
                # push a future DISPATCH event so they're not stranded
                if waiters:
                    next_free = charger_free[sid][0]
                    heapq.heappush(global_heap, _Event(
                        time=next_free, ev_type=_EvType.DISPATCH,
                        bus_id="", station_id=sid,
                    ))

        # Guard: buses whose final_arrival was never set (no charges — edge case)
        for bus_id, state in bus_states.items():
            if bus_id not in final_arrivals:
                dest_d = config.route.cumulative_distance_from_origin(
                    self._dest(state.bus, config.route), state.bus.direction
                )
                final_arrivals[bus_id] = (
                    state.bus.departure_min + dest_d / config.route.speed_kmh * 60.0
                )

        return final_arrivals

    def _pick_best(
        self,
        waiters: List[_Waiter],
        station_id: str,
        bus_states: Dict[str, _BusState],
        scorer: WeightedScorer,
    ) -> _Waiter:
        """Return the highest-scoring (most urgent) waiter."""
        operator_fleet_waits: Dict[str, List[float]] = defaultdict(list)
        all_bus_waits: Dict[str, float] = {}
        for sid, s in bus_states.items():
            w = sum(e.wait_min for e in s.events)
            operator_fleet_waits[s.bus.operator].append(w)
            all_bus_waits[sid] = w

        def score(w: _Waiter) -> float:
            state = bus_states[w.bus_id]
            current_wait = sum(e.wait_min for e in state.events)
            return scorer.score(
                bus_id=w.bus_id,
                operator=state.bus.operator,
                current_wait_min=current_wait,
                operator_fleet_waits=dict(operator_fleet_waits),
                all_bus_waits=all_bus_waits,
            )

        # Highest score = most urgent = goes first
        # Tie-break by bus_id for determinism
        return max(waiters, key=lambda w: (score(w), w.bus_id))

    # ─────────────────────────── plan reassignment ────────────────────────────

    def _try_reassign(
        self,
        bus_states: Dict[str, _BusState],
        config: ScenarioConfig,
        valid_plans: Dict[Direction, List[List[str]]],
        plans_tried: Dict[str, set],
    ) -> bool:
        reassigned = False
        for bus_id, state in bus_states.items():
            if state.total_wait <= self._threshold:
                continue
            congested = (
                max(state.events, key=lambda e: e.wait_min).station_id
                if state.events else None
            )
            plans_tried[bus_id].add(tuple(state.plan))
            for candidate in valid_plans[state.bus.direction]:
                key = tuple(candidate)
                if key in plans_tried[bus_id]:
                    continue
                if congested and congested not in candidate:
                    state.plan = candidate
                    reassigned = True
                    break
        return reassigned

    # ─────────────────────────── helpers ──────────────────────────────────────

    def _eta(self, state: _BusState, station_id: str, config: ScenarioConfig) -> float:
        """ETA for this bus to reach station_id from its current position."""
        from_stop = (
            state.events[-1].station_id if state.events
            else (
                config.route.terminals[0]
                if state.bus.direction == Direction.BK
                else config.route.terminals[1]
            )
        )
        route = config.route
        d = abs(
            route.cumulative_distance_from_origin(station_id, state.bus.direction)
            - route.cumulative_distance_from_origin(from_stop, state.bus.direction)
        )
        return state.current_time + d / route.speed_kmh * 60.0

    def _dest(self, bus: Bus, route: Route) -> str:
        o, d = route.terminals
        return d if bus.direction == Direction.BK else o

    def _build_result(
        self,
        config: ScenarioConfig,
        bus_states: Dict[str, _BusState],
        final_arrivals: Dict[str, float],
    ) -> ScheduleResult:
        timelines: Dict[str, BusTimeline] = {}
        station_queues: Dict[str, StationQueue] = {
            s.id: StationQueue(station=s) for s in config.route.charging_stations
        }
        for bus_id, state in bus_states.items():
            timelines[bus_id] = BusTimeline(
                bus=state.bus,
                charging_plan=[e.station_id for e in state.events],
                charge_events=list(state.events),
                final_arrival_min=final_arrivals.get(bus_id, 0.0),
            )
            for event in state.events:
                station_queues[event.station_id].add_event(event)
        return ScheduleResult(
            scenario=config,
            bus_timelines=timelines,
            station_queues=station_queues,
        )
