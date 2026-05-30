"""
StationQueueView: renders per-station charging order and queue details.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.models import ScheduleResult
from ui.formatting import (
    fmt_time, fmt_dur, operator_badge, wait_color,
    station_color, OPERATOR_COLORS
)


def render(result: ScheduleResult) -> None:
    st.markdown("### 🔌 Per-Station Charging Order")

    station_queues = result.station_queues
    config = result.scenario

    if not station_queues:
        st.info("No station data available.")
        return

    # One column per station
    station_ids = [s.id for s in config.route.charging_stations]
    cols = st.columns(len(station_ids))

    for col, sid in zip(cols, station_ids):
        queue = station_queues.get(sid)
        with col:
            sc = station_color(sid)
            st.markdown(
                f"<div style='background:{sc}15;border-left:4px solid {sc};"
                f"padding:8px 12px;border-radius:4px;margin-bottom:8px'>"
                f"<span style='font-size:18px;font-weight:800;color:{sc}'>Station {sid}</span><br>"
                f"<span style='font-size:11px;color:#666'>"
                f"{len(queue.events) if queue else 0} buses · "
                f"{queue.utilisation_pct if queue else 0:.0f}% utilisation"
                f"</span></div>",
                unsafe_allow_html=True
            )

            if not queue or not queue.events:
                st.markdown("<span style='color:#999;font-size:12px'>No buses charged here</span>", unsafe_allow_html=True)
                continue

            for i, event in enumerate(queue.events):
                op = _get_operator(event.bus_id, config)
                op_color = OPERATOR_COLORS.get(op, "#888")
                wc = wait_color(event.wait_min)

                st.markdown(
                    f"<div style='border:1px solid #E5E7EB;border-radius:6px;"
                    f"padding:8px;margin:4px 0;background:#FAFAFA'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center'>"
                    f"<span style='font-weight:700;font-size:13px;color:#111'>#{i+1} {event.bus_id}</span>"
                    f"<span style='background:{op_color}20;color:{op_color};border:1px solid {op_color};"
                    f"border-radius:3px;padding:1px 5px;font-size:10px;font-weight:700'>"
                    f"{op.upper()}</span>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#666;margin-top:4px'>"
                    f"Arrives: <b>{_t(event.arrival_min)}</b>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#666'>"
                    f"Wait: <b style='color:{wc}'>{fmt_dur(event.wait_min) if event.wait_min > 0 else 'None'}</b>"
                    f"</div>"
                    f"<div style='font-size:11px;color:#666'>"
                    f"Charges: <b>{_t(event.charge_start_min)} → {_t(event.charge_end_min)}</b>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )

    st.divider()

    # Comparative table
    st.markdown("**Station Summary**")
    summary_rows = []
    for sid in station_ids:
        queue = station_queues.get(sid)
        if not queue or not queue.events:
            summary_rows.append({
                "Station": sid,
                "Buses Served": 0,
                "Peak Queue": 0,
                "Utilisation %": 0,
                "Max Wait (min)": 0,
                "Avg Wait (min)": 0,
            })
            continue

        waits = [e.wait_min for e in queue.events]
        summary_rows.append({
            "Station": sid,
            "Buses Served": len(queue.events),
            "Peak Queue": queue.peak_queue_length,
            "Utilisation %": queue.utilisation_pct,
            "Max Wait (min)": round(max(waits), 1),
            "Avg Wait (min)": round(sum(waits) / len(waits), 1),
        })

    st.dataframe(pd.DataFrame(summary_rows), use_container_width=True, hide_index=True)


def _get_operator(bus_id: str, config) -> str:
    for bus in config.buses:
        if bus.id == bus_id:
            return bus.operator
    return "unknown"


def _t(minutes: float) -> str:
    import re
    from ui.formatting import fmt_time
    return re.sub(r"<[^>]+>", "", fmt_time(minutes))
