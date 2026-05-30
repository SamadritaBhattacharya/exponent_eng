"""
BusTimetableView: renders per-bus full timeline.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.models import ScheduleResult, Direction
from ui.formatting import (
    fmt_time, fmt_dur, operator_badge, direction_badge,
    wait_badge, station_badge, wait_color, OPERATOR_COLORS
)


def render(result: ScheduleResult) -> None:
    st.markdown("### 🚌 Per-Bus Timetable")

    config = result.scenario
    timelines = result.bus_timelines

    # Filter controls
    col1, col2, col3 = st.columns(3)
    with col1:
        operators = sorted(set(tl.bus.operator for tl in timelines.values()))
        selected_ops = st.multiselect(
            "Filter by operator",
            options=operators,
            default=operators,
            format_func=lambda x: x.upper(),
            key="timetable_ops"
        )
    with col2:
        directions = ["BK", "KB"]
        selected_dirs = st.multiselect(
            "Filter by direction",
            options=directions,
            default=directions,
            format_func=lambda x: "Bengaluru→Kochi" if x == "BK" else "Kochi→Bengaluru",
            key="timetable_dirs"
        )
    with col3:
        sort_by = st.selectbox(
            "Sort by",
            ["Departure", "Total Wait", "Total Trip Time", "Bus ID"],
            key="timetable_sort"
        )

    # Build display dataframe
    rows = []
    for bus_id, tl in timelines.items():
        if tl.bus.operator not in selected_ops:
            continue
        if tl.bus.direction.value not in selected_dirs:
            continue

        origin = "Bengaluru" if tl.bus.direction == Direction.BK else "Kochi"
        dest = "Kochi" if tl.bus.direction == Direction.BK else "Bengaluru"

        charge_summary = " → ".join(e.station_id for e in tl.charge_events)

        rows.append({
            "Bus ID": bus_id,
            "Operator": tl.bus.operator.upper(),
            "Direction": "BK→" if tl.bus.direction == Direction.BK else "KB→",
            "Departs": _strip_html(fmt_time(tl.bus.departure_min)),
            "Charges at": charge_summary,
            "Arrives": _strip_html(fmt_time(tl.final_arrival_min)),
            "Total Wait": tl.total_wait_min,
            "Charging Time": tl.total_charge_min,
            "Trip Duration": tl.total_trip_min,
            "_tl": tl,
        })

    sort_map = {
        "Departure": lambda r: r["_tl"].bus.departure_min,
        "Total Wait": lambda r: r["Total Wait"],
        "Total Trip Time": lambda r: r["Trip Duration"],
        "Bus ID": lambda r: r["Bus ID"],
    }
    rows.sort(key=sort_map[sort_by])

    if not rows:
        st.info("No buses match the selected filters.")
        return

    # Summary bar
    total_wait = sum(r["Total Wait"] for r in rows)
    avg_wait = total_wait / len(rows)
    max_wait = max(r["Total Wait"] for r in rows)
    scols = st.columns(4)
    scols[0].metric("Buses shown", len(rows))
    scols[1].metric("Avg wait", fmt_dur(avg_wait))
    scols[2].metric("Max wait", fmt_dur(max_wait))
    scols[3].metric("Total delay", fmt_dur(total_wait))

    st.divider()

    # Per-bus cards
    for row in rows:
        tl = row["_tl"]
        _render_bus_card(tl, config)


def _render_bus_card(tl, config) -> None:
    operator = tl.bus.operator
    color = OPERATOR_COLORS.get(operator, "#888")
    direction_str = tl.bus.direction.value

    with st.container():
        # Header row
        h1, h2, h3, h4 = st.columns([2, 2, 2, 2])
        with h1:
            st.markdown(
                f"**{tl.bus.id}** &nbsp; "
                f"<span style='background:{color}20;color:{color};"
                f"border:1px solid {color};border-radius:3px;"
                f"padding:1px 6px;font-size:11px;font-weight:700'>"
                f"{operator.upper()}</span>",
                unsafe_allow_html=True
            )
        with h2:
            label = "Bengaluru → Kochi" if tl.bus.direction.value == "BK" else "Kochi → Bengaluru"
            st.markdown(f"<span style='font-size:12px;color:#666'>{label}</span>", unsafe_allow_html=True)
        with h3:
            st.markdown(
                f"<span style='font-size:12px'>Trip: <b>{fmt_dur(tl.total_trip_min)}</b></span>",
                unsafe_allow_html=True
            )
        with h4:
            wc = wait_color(tl.total_wait_min)
            wt = f"Wait: <b style='color:{wc}'>{fmt_dur(tl.total_wait_min)}</b>"
            st.markdown(f"<span style='font-size:12px'>{wt}</span>", unsafe_allow_html=True)

        # Timeline table
        origin = "Bengaluru" if tl.bus.direction.value == "BK" else "Kochi"
        dest = "Kochi" if tl.bus.direction.value == "BK" else "Bengaluru"

        table_rows = []
        table_rows.append({
            "Event": f"🟢 Depart {origin}",
            "Time": _strip_html(fmt_time(tl.bus.departure_min)),
            "Wait": "—",
            "Charge": "—",
            "Departs": "—",
        })

        for event in tl.charge_events:
            table_rows.append({
                "Event": f"⚡ Charge at {event.station_id}",
                "Time": _strip_html(fmt_time(event.arrival_min)),
                "Wait": fmt_dur(event.wait_min) if event.wait_min > 0 else "None",
                "Charge": f"{_strip_html(fmt_time(event.charge_start_min))} – {_strip_html(fmt_time(event.charge_end_min))}",
                "Departs": _strip_html(fmt_time(event.charge_end_min)),
            })

        table_rows.append({
            "Event": f"🏁 Arrive {dest}",
            "Time": _strip_html(fmt_time(tl.final_arrival_min)),
            "Wait": "—",
            "Charge": "—",
            "Departs": "—",
        })

        df = pd.DataFrame(table_rows)
        st.dataframe(df, use_container_width=True, hide_index=True, height=_table_height(len(table_rows)))
        st.markdown("---")


def _table_height(n_rows: int) -> int:
    return min(38 * (n_rows + 1) + 10, 400)


def _strip_html(s: str) -> str:
    import re
    return re.sub(r"<[^>]+>", "", s)
