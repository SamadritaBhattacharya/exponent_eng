"""
UI formatting utilities.
Converts internal float minutes to display strings, color-codes operators, etc.
"""
from __future__ import annotations
from typing import Dict


OPERATOR_COLORS: Dict[str, str] = {
    "kpn":      "#E8A838",
    "freshbus": "#4CAF97",
    "flixbus":  "#9B59B6",
}

OPERATOR_BG: Dict[str, str] = {
    "kpn":      "#FFF8E7",
    "freshbus": "#F0FAF7",
    "flixbus":  "#F5F0FA",
}

DIRECTION_LABEL = {
    "BK": "Bengaluru → Kochi",
    "KB": "Kochi → Bengaluru",
}


def fmt_time(minutes: float) -> str:
    """Convert absolute minutes from midnight to HH:MM. Handles next-day."""
    total = int(round(minutes))
    day_offset = total // (24 * 60)
    total = total % (24 * 60)
    h = total // 60
    m = total % 60
    s = f"{h:02d}:{m:02d}"
    if day_offset > 0:
        s += f" <span style='font-size:10px;color:#999'>(+{day_offset}d)</span>"
    return s


def fmt_dur(minutes: float) -> str:
    """Format duration e.g. '1h 32m' or '25m'."""
    minutes = round(minutes)
    if minutes < 60:
        return f"{minutes}m"
    h = minutes // 60
    m = minutes % 60
    if m == 0:
        return f"{h}h"
    return f"{h}h {m}m"


def operator_badge(operator: str) -> str:
    color = OPERATOR_COLORS.get(operator, "#888")
    bg = OPERATOR_BG.get(operator, "#F5F5F5")
    label = operator.upper()
    return (
        f"<span style='background:{bg};color:{color};border:1.5px solid {color};"
        f"border-radius:4px;padding:2px 8px;font-size:11px;"
        f"font-weight:700;letter-spacing:0.5px'>{label}</span>"
    )


def direction_badge(direction_str: str) -> str:
    label = DIRECTION_LABEL.get(direction_str, direction_str)
    if direction_str == "BK":
        return f"<span style='color:#2563EB;font-weight:600;font-size:12px'>▶ {label}</span>"
    return f"<span style='color:#DC2626;font-weight:600;font-size:12px'>◀ {label}</span>"


def wait_color(wait_min: float) -> str:
    """Traffic-light color for wait duration."""
    if wait_min == 0:
        return "#22C55E"
    if wait_min <= 25:
        return "#F59E0B"
    if wait_min <= 50:
        return "#EF4444"
    return "#7C2D12"


def wait_badge(wait_min: float) -> str:
    color = wait_color(wait_min)
    text = "No wait" if wait_min == 0 else f"+{fmt_dur(wait_min)}"
    bg = "#F0FDF4" if wait_min == 0 else "#FEF3C7" if wait_min <= 25 else "#FEE2E2"
    return (
        f"<span style='background:{bg};color:{color};border:1px solid {color};"
        f"border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600'>{text}</span>"
    )


def station_color(station_id: str) -> str:
    palette = {"A": "#3B82F6", "B": "#10B981", "C": "#F59E0B", "D": "#EF4444"}
    return palette.get(station_id, "#6B7280")


def station_badge(station_id: str) -> str:
    color = station_color(station_id)
    return (
        f"<span style='background:{color}20;color:{color};border:1.5px solid {color};"
        f"border-radius:50%;padding:2px 8px;font-size:12px;font-weight:700'>{station_id}</span>"
    )
