# Architecture

## Scheduling Approach: Event-Driven Simulation

### Why This Approach

The problem is inherently temporal. Buses move through time, arrive at stations, contend for chargers, and their delays propagate forward. An event-driven simulation models this directly:

- Each "bus arrives at station" is an event, processed in chronological order
- When two buses want the same charger, a weighted scoring function decides priority
- Delays automatically cascade: if bus A waits at B, its late arrival at C creates new contention there
- Adding a new rule = adding a new scoring function; the engine never changes

Alternatives considered:
- **Constraint programming (OR-Tools)**: Powerful but hard to add soft rules incrementally. Also heavyweight for 20 buses.
- **Genetic algorithm**: Good search, poor explainability. Hard to guarantee correctness.
- **Integer linear program**: Optimal but opaque and inflexible; weights require reformulating the model.

Event-driven simulation wins because it is inspectable, extendable, and correct by construction.

---

## Data Structure Design

### The Core Principle

Every parameter that could change is a data field, not a constant.

```
ScenarioConfig
├── Route
│   ├── segments: List[Segment]      ← distances are data, not code
│   ├── charging_stations: List[Station]
│   │   ├── num_chargers: int        ← 1 today, 3 tomorrow: one field
│   │   └── charge_time_min: float   ← per-station override supported
│   └── speed_kmh: float             ← per-route speed
├── buses: List[Bus]
│   ├── battery_range_km: float      ← per-bus range for mixed fleets
│   └── priority: int                ← express/premium override
└── weights: Weights
    ├── individual: float
    ├── operator: float
    └── overall: float
```

---

## Anticipated Future Changes and How the Design Handles Them

### 1. More stations along the route
**Handle:** `route.segments` and `route.charging_stations` are lists. Add entries to both in the JSON. Zero code changes.

### 2. Multiple chargers per station
**Handle:** `station.num_chargers = 3`. `ChargerManager` uses a min-heap of size `num_chargers`. Already supported. One JSON field.

### 3. More buses (50, 100, 500)
**Handle:** `buses` is a list. The event-driven simulation is O(n log n) in the number of buses. Add buses to the JSON.

### 4. New operators
**Handle:** `bus.operator` is a free-form string. The scoring rules group by string value. No enum, no code change.

### 5. Heterogeneous battery ranges (different bus models)
**Handle:** `bus.battery_range_km` is a per-bus field. `ChargingPlanGenerator` receives this per-bus range. Already supported.

### 6. Per-station charge times (fast charger at B)
**Handle:** `station.charge_time_min` is already a per-station field. Change it in the JSON.

### 7. Different speeds per route segment
**Handle:** `Segment` model has `distance_km`. Add `speed_kmh` to `Segment` and use it in `Route.travel_time_min()`. One field addition, no structural change.

### 8. Priority buses (express, VIP)
**Handle:** `bus.priority: int` already exists. `PriorityRule` in `scoring.py` reads it. Wire it to the `WeightedScorer` with a `priority_weight` in the scenario JSON.

### 9. Time-of-day electricity pricing
**Handle:** Add a `pricing_schedule: List[{from_min, to_min, cost}]` to `Station`. Add a `TimeOfDayPricingRule` in `scoring.py` that penalises charging during expensive windows. No engine changes.

### 10. Multiple routes sharing stations
**Handle:** `Station` is independent of `Route`. A station can appear in multiple route definitions. The scheduler assigns chargers per-station regardless of which route uses it. Add a `shared_stations` concept to the JSON config.

### 11. Driver shift constraints
**Handle:** Add `max_trip_duration_min` to `Bus`. Add a `DriverShiftRule` in `validator.py`. Already-extensible validator.

### 12. Bidirectional routes with asymmetric station distances
**Handle:** `Route.cumulative_distance_from_origin(stop, direction)` is already direction-aware. Reversing the segment list for KB direction is already implemented.

### 13. More objective weights (e.g. carbon cost, punctuality index)
**Handle:** Add a new `ScoringRule` subclass. Add a weight field to `Weights`. Add it to `WeightedScorer.from_weights()`. Three lines. No engine changes.

### 14. Live scenario editing via UI
**Handle:** `ScenarioConfig` is a plain Python dataclass. A UI form can build one in-memory without touching any files.

### 15. A/B testing two scheduling strategies
**Handle:** `Scheduler` is a class. Subclass it with `GreedyScheduler` and `FairRoundRobinScheduler`. Pass either to the app.

---

## SOLID Principles Applied

| Principle | How |
|---|---|
| **Single Responsibility** | `ChargingPlanGenerator` only enumerates plans. `Scheduler` only simulates. `ScheduleValidator` only validates. `ScenarioLoader` only parses. |
| **Open/Closed** | New scoring rule = new class, no changes to `Scheduler`. New hard rule = new method in `ScheduleValidator`. |
| **Liskov Substitution** | `ScoringRule` subclasses are interchangeable. `WeightedScorer` accepts any list of rules. |
| **Interface Segregation** | `ScoringRule` has one method: `penalty()`. `ChargerManager` has three: `next_available_after`, `book`, `reset`. |
| **Dependency Inversion** | `Scheduler` depends on `WeightedScorer` and `ChargingPlanGenerator` abstractions, not on specific rule implementations. |

---

## Assumptions

1. **Speed is constant across all segments and buses** (60 km/h unless overridden in the scenario).
2. **Waiting at a station does not consume battery.** Buses are parked; range only decrements while driving.
3. **Charging always fills to full (240 km range)**, regardless of how much range the bus had on arrival.
4. **Zero switchover time** between buses at a charger. Bus A finishes at t=100; Bus B can start at t=100.
5. **Departure times are from midnight day 1.** Times below 18:00 are not expected; any time is valid as a float.
6. **Terminus charging (Bengaluru, Kochi) is not scheduled.** Every bus starts with full charge; terminus charging is assumed complete before departure.
7. **Tie-breaking is by bus ID (alphabetical)** when two buses arrive at the same station at the identical minute. This is deterministic and reproducible.
8. **Plan reassignment is a best-effort heuristic.** If the scheduler can't improve a bus's wait by switching plans (all alternatives are also congested, or all plans have been tried), it keeps the original plan. The schedule remains valid regardless.

---

## How to Change a Weight (Concrete Example)

**Scenario 4 currently has `operator = 2.0`.** To set it to `3.0`:

```json
// data/scenarios/scenario_4.json
"weights": {
  "individual": 1.0,
  "operator": 3.0,
  "overall": 1.0
}
```

Reload the app. The scheduler re-runs with the new weight. No code touched.

---

## How to Add a New Rule (Concrete Example)

Add a rule that discourages charging the same bus twice at the same station (future: battery health policy):

```python
# core/scoring.py — add this class

class NoDuplicateStationRule(ScoringRule):
    """Penalise a bus that has already charged at this station on a previous trip."""

    @property
    def name(self) -> str:
        return "no_duplicate_station"

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        # Implementation: look up bus history; return high penalty if repeat station
        return 0.0
```

Then in `WeightedScorer.from_weights()`:

```python
return cls([
    (IndividualWaitRule(),     weights.individual),
    (OperatorFairnessRule(),   weights.operator),
    (OverallSystemRule(),      weights.overall),
    (NoDuplicateStationRule(), weights.get("no_duplicate", 0.0)),  # new line
])
```

Add `"no_duplicate": 1.5` to the scenario JSON weights block. Done.
