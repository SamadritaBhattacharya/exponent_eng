"""
ScenarioInputView: renders the raw scenario data so reviewers can see what was fed in.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.models import ScenarioConfig, Direction
from ui.formatting import operator_badge, direction_badge, fmt_time, station_badge


def render(config: ScenarioConfig) -> None:
    st.markdown("### 📋 Scenario Input")

    # Meta card
    cols = st.columns([2, 1, 1, 1])
    with cols[0]:
        st.markdown(f"**{config.name}**")
        st.caption(config.description)
    with cols[1]:
        st.metric("Buses", len(config.buses))
    with cols[2]:
        st.metric("Battery Range", f"{config.default_battery_range_km:.0f} km")
    with cols[3]:
        st.metric("Speed", f"{config.default_speed_kmh:.0f} km/h")

    # Weights
    st.markdown("**Objective Weights**")
    w = config.weights
    wcols = st.columns(3)
    wcols[0].metric("Individual", w.individual, help="Penalises long waits for any single bus")
    wcols[1].metric("Operator", w.operator, help="Penalises uneven fleet-level delays")
    wcols[2].metric("Overall", w.overall, help="Penalises high total system delay")

    st.divider()

    # Route
    st.markdown("**Route**")
    route = config.route
    seg_data = []
    cumulative = 0
    for seg in route.segments:
        seg_data.append({
            "From": seg.from_stop,
            "To": seg.to_stop,
            "Distance (km)": seg.distance_km,
            "Travel Time": f"{seg.distance_km / route.speed_kmh * 60:.0f} min",
            "Cumulative (km)": cumulative + seg.distance_km,
        })
        cumulative += seg.distance_km
    st.dataframe(pd.DataFrame(seg_data), use_container_width=True, hide_index=True)

    # Stations
    st.markdown("**Charging Stations**")
    station_data = [
        {
            "Station": s.id,
            "Name": s.name,
            "Chargers": s.num_chargers,
            "Charge Time (min)": s.charge_time_min,
        }
        for s in route.charging_stations
    ]
    st.dataframe(pd.DataFrame(station_data), use_container_width=True, hide_index=True)

    st.divider()

    # Bus fleet
    st.markdown("**Bus Fleet**")
    bus_rows = []
    for bus in sorted(config.buses, key=lambda b: (b.direction.value, b.departure_min)):
        bus_rows.append({
            "Bus ID": bus.id,
            "Operator": bus.operator.upper(),
            "Direction": "Bengaluru → Kochi" if bus.direction == Direction.BK else "Kochi → Bengaluru",
            "Departure": fmt_time(bus.departure_min).replace("<span style='font-size:10px;color:#999'>", "").replace("</span>", ""),
            "Range (km)": bus.battery_range_km,
            "Priority": bus.priority,
        })
    st.dataframe(pd.DataFrame(bus_rows), use_container_width=True, hide_index=True)
