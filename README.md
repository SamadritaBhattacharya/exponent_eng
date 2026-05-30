# Bus Charging Scheduler

Event-driven simulation for scheduling electric bus charging along the Bengaluru–Kochi corridor.

Deployed Link: https://exponenteng-bus-scheduler.streamlit.app

## Quick Start

```bash
git clone <repo>
cd bus_scheduler
pip install -r requirements.txt
streamlit run app.py
```

App opens at `http://localhost:8501`.

---

## How to Change a Weight

Open the scenario JSON file (e.g. `data/scenarios/scenario_4.json`). Find the `weights` block:

```json
"weights": {
  "individual": 1.0,
  "operator": 2.0,
  "overall": 1.0
}
```

Change any value and reload the app. No code changes needed.

---

## How to Add a New Scenario

Create a new JSON file in `data/scenarios/`. Minimum required fields:

```json
{
  "id": "scenario_6",
  "name": "My New Scenario",
  "description": "...",
  "weights": { "individual": 1.0, "operator": 1.0, "overall": 1.0 },
  "route": { ... },
  "buses": [ ... ]
}
```

The app auto-discovers all `.json` files in `data/scenarios/` on startup.

---

## How to Add a New Soft Rule

1. Open `core/scoring.py`
2. Add a new class inheriting from `ScoringRule`:

```python
class TimeOfDayPricingRule(ScoringRule):
    """Prefer charging during off-peak hours (lower electricity cost)."""

    @property
    def name(self) -> str:
        return "time_of_day"

    def penalty(self, bus_id, operator, current_wait_min, operator_fleet_waits, all_bus_waits) -> float:
        # Lower penalty during off-peak hours encourages off-peak charging
        return 0.0  # implement your logic here
```

3. Add a weight for it in `WeightedScorer.from_weights()` or wire it from a new scenario field.

Zero changes to the scheduler engine.

---

## How to Add a New Hard Rule

Open `core/validator.py`, add a `_check_*` method, and call it from `validate()`:

```python
def _check_driver_shift(self, result: ScheduleResult) -> List[ValidationError]:
    errors = []
    for bus_id, tl in result.bus_timelines.items():
        if tl.total_trip_min > 600:  # 10-hour shift limit
            errors.append(ValidationError(bus_id, "SHIFT", f"Trip {tl.total_trip_min:.0f} min exceeds shift limit"))
    return errors
```

---

## Project Structure

```
bus_scheduler/
├── app.py                   # Streamlit entry point
├── requirements.txt
├── core/
│   ├── models.py            # Domain objects (Route, Bus, Weights, ScheduleResult …)
│   ├── plan_generator.py    # Enumerate all valid charging plans
│   ├── scoring.py           # Pluggable soft rules (Individual, Operator, Overall …)
│   ├── charger_manager.py   # Per-station charger slot tracking
│   ├── scheduler.py         # Event-driven simulation engine
│   ├── validator.py         # POST-phase hard constraint checks
│   └── loader.py            # JSON → ScenarioConfig, time parsing
├── ui/
│   ├── formatting.py        # Shared display helpers
│   └── components/
│       ├── scenario_view.py # Tab 1: raw scenario input
│       ├── bus_timetable.py # Tab 2: per-bus timeline
│       ├── station_view.py  # Tab 3: per-station queue
│       └── operator_view.py # Tab 4: operator stats
└── data/
    └── scenarios/
        ├── scenario_1.json  # Even spacing
        ├── scenario_2.json  # Bunched start
        ├── scenario_3.json  # Asymmetric load
        ├── scenario_4.json  # Operator heavy
        └── scenario_5.json  # Worst case convergence
```
