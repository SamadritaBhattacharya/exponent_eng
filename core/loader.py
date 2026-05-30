"""
ScenarioLoader: reads JSON scenario files and hydrates ScenarioConfig objects.

Validates all fields at load time (PRE phase).
Raises descriptive errors for missing or invalid data.

Single Responsibility: I/O and deserialization only.
"""

from __future__ import annotations
import json
import os
from typing import List
from core.models import (
    Bus, Direction, Route, Segment, Station, Weights,
    ScenarioConfig
)


class ScenarioLoadError(Exception):
    pass


class ScenarioLoader:
    """Loads scenario files from a directory."""

    def __init__(self, scenarios_dir: str):
        self._dir = scenarios_dir

    def list_scenarios(self) -> List[str]:
        """Return sorted list of scenario file paths."""
        files = [
            f for f in os.listdir(self._dir)
            if f.endswith(".json")
        ]
        return sorted(os.path.join(self._dir, f) for f in files)

    def load(self, filepath: str) -> ScenarioConfig:
        """Load and validate a scenario from a JSON file."""
        try:
            with open(filepath, "r") as fh:
                raw = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise ScenarioLoadError(f"Cannot read {filepath}: {exc}") from exc

        return self._parse(raw, filepath)

    def load_all(self) -> List[ScenarioConfig]:
        return [self.load(fp) for fp in self.list_scenarios()]

    # ─────────────────────────── parser ───────────────────────────────────────

    def _parse(self, raw: dict, src: str) -> ScenarioConfig:
        try:
            route = self._parse_route(raw["route"])
            buses = [self._parse_bus(b, route) for b in raw["buses"]]
            weights = self._parse_weights(raw.get("weights", {}))
            self._validate_no_duplicate_ids(buses, src)

            return ScenarioConfig(
                id=self._req(raw, "id", src),
                name=self._req(raw, "name", src),
                description=raw.get("description", ""),
                route=route,
                buses=buses,
                weights=weights,
                default_battery_range_km=float(raw.get("battery_range_km", 240.0)),
                default_charge_time_min=float(raw.get("charge_time_min", 25.0)),
                default_speed_kmh=float(raw.get("speed_kmh", 60.0)),
            )
        except KeyError as exc:
            raise ScenarioLoadError(f"Missing field {exc} in {src}") from exc

    def _parse_route(self, raw: dict) -> Route:
        segments = [
            Segment(
                from_stop=s["from"],
                to_stop=s["to"],
                distance_km=float(s["distance_km"])
            )
            for s in raw["segments"]
        ]
        stations = [
            Station(
                id=s["id"],
                name=s["name"],
                num_chargers=int(s.get("num_chargers", 1)),
                charge_time_min=float(s.get("charge_time_min", 25.0)),
            )
            for s in raw["stations"]
        ]
        return Route(
            id=raw["id"],
            segments=segments,
            charging_stations=stations,
            speed_kmh=float(raw.get("speed_kmh", 60.0)),
        )

    def _parse_bus(self, raw: dict, route: Route) -> Bus:
        direction_str = raw["direction"].upper()
        try:
            direction = Direction[direction_str]
        except KeyError:
            raise ScenarioLoadError(
                f"Bus '{raw.get('id', '?')}' has unknown direction '{direction_str}'. "
                f"Use 'BK' or 'KB'."
            )
        return Bus(
            id=raw["id"],
            operator=raw["operator"].lower(),
            direction=direction,
            departure_min=self._parse_time(raw["departure"], raw["id"]),
            route_id=route.id,
            battery_range_km=float(raw.get("battery_range_km", 240.0)),
            priority=int(raw.get("priority", 0)),
        )

    def _parse_weights(self, raw: dict) -> Weights:
        return Weights(
            individual=float(raw.get("individual", 1.0)),
            operator=float(raw.get("operator", 1.0)),
            overall=float(raw.get("overall", 1.0)),
        )

    @staticmethod
    def _parse_time(time_str: str, bus_id: str) -> float:
        """
        Parse 'HH:MM' into minutes from midnight day 1.
        Times < 19:00 are assumed to be next-day (e.g. '01:30' → 25.5 hours).
        """
        try:
            h, m = map(int, time_str.split(":"))
        except (ValueError, AttributeError):
            raise ScenarioLoadError(f"Bus {bus_id}: invalid departure time '{time_str}'")
        if h < 0 or h > 23 or m < 0 or m > 59:
            raise ScenarioLoadError(f"Bus {bus_id}: time '{time_str}' out of range")
        return float(h * 60 + m)

    @staticmethod
    def _req(raw: dict, key: str, src: str):
        if key not in raw:
            raise ScenarioLoadError(f"Required field '{key}' missing in {src}")
        return raw[key]

    @staticmethod
    def _validate_no_duplicate_ids(buses: List[Bus], src: str) -> None:
        ids = [b.id for b in buses]
        if len(ids) != len(set(ids)):
            duplicates = [i for i in ids if ids.count(i) > 1]
            raise ScenarioLoadError(f"Duplicate bus IDs in {src}: {set(duplicates)}")


def format_minutes(minutes: float) -> str:
    """Convert absolute minutes from midnight to HH:MM string."""
    total = int(round(minutes))
    days_extra = total // (24 * 60)
    total = total % (24 * 60)
    h = total // 60
    m = total % 60
    base = f"{h:02d}:{m:02d}"
    if days_extra > 0:
        base += f" (+{days_extra}d)"
    return base
