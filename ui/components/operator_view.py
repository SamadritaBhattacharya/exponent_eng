"""
OperatorStatsView: renders per-operator fleet statistics.
"""
from __future__ import annotations
import streamlit as st
import pandas as pd
from core.models import ScheduleResult
from ui.formatting import fmt_dur, OPERATOR_COLORS


def render(result: ScheduleResult) -> None:
    st.markdown("### 🏢 Operator Fleet Summary")

    stats = result.operator_stats()
    sys = result.system_stats()

    # System-level summary
    sc = st.columns(4)
    sc[0].metric("Total Buses", sys.get("total_buses", 0))
    sc[1].metric("Total Wait (all buses)", fmt_dur(sys.get("total_wait_min", 0)))
    sc[2].metric("Max Single Wait", fmt_dur(sys.get("max_single_wait_min", 0)))
    sc[3].metric("Avg Trip Time", fmt_dur(sys.get("avg_trip_min", 0)))

    st.divider()

    # Per-operator cards
    op_cols = st.columns(len(stats))
    for col, (op, data) in zip(op_cols, stats.items()):
        color = OPERATOR_COLORS.get(op, "#888")
        with col:
            st.markdown(
                f"<div style='background:{color}15;border:1.5px solid {color};"
                f"border-radius:8px;padding:14px;text-align:center'>"
                f"<div style='font-size:18px;font-weight:800;color:{color}'>{op.upper()}</div>"
                f"<div style='font-size:12px;color:#666;margin-bottom:8px'>{data['count']} buses</div>"
                f"<div style='font-size:13px;margin:3px 0'>"
                f"Avg wait: <b style='color:{color}'>{fmt_dur(data['avg_wait'])}</b></div>"
                f"<div style='font-size:13px;margin:3px 0'>"
                f"Max wait: <b>{fmt_dur(data['max_wait'])}</b></div>"
                f"<div style='font-size:13px;margin:3px 0'>"
                f"Avg trip: <b>{fmt_dur(data['avg_trip'])}</b></div>"
                f"</div>",
                unsafe_allow_html=True
            )

    st.divider()

    # Table view
    st.markdown("**Detailed Operator Stats**")
    table = [
        {
            "Operator": op.upper(),
            "Fleet Size": d["count"],
            "Avg Wait": fmt_dur(d["avg_wait"]),
            "Max Wait": fmt_dur(d["max_wait"]),
            "Total Wait": fmt_dur(d["total_wait"]),
            "Avg Trip": fmt_dur(d["avg_trip"]),
        }
        for op, d in stats.items()
    ]
    st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)
