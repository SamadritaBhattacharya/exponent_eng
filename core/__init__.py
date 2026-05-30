"""Public API for the bus_scheduler core."""
from core.models import (
    Bus, Direction, Route, Segment, Station, Weights,
    ScenarioConfig, ChargeEvent, BusTimeline, StationQueue, ScheduleResult
)
from core.scheduler import Scheduler
from core.loader import ScenarioLoader, ScenarioLoadError, format_minutes
from core.validator import ScheduleValidator, ValidationError
from core.plan_generator import ChargingPlanGenerator
from core.scoring import WeightedScorer, IndividualWaitRule, OperatorFairnessRule, OverallSystemRule

__all__ = [
    "Bus", "Direction", "Route", "Segment", "Station", "Weights",
    "ScenarioConfig", "ChargeEvent", "BusTimeline", "StationQueue", "ScheduleResult",
    "Scheduler", "ScenarioLoader", "ScenarioLoadError", "format_minutes",
    "ScheduleValidator", "ValidationError",
    "ChargingPlanGenerator", "WeightedScorer",
]
