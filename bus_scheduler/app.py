"""
Bus Charging Scheduler — Streamlit App
Entry point: streamlit run app.py

Architecture:
  core/     — pure Python, no Streamlit imports
  ui/       — Streamlit rendering only, imports from core
  data/     — scenario JSON files
  app.py    — wires core and ui together, owns session state
"""

import os
import sys
import streamlit as st

# Ensure project root is on path (needed for Streamlit Cloud)
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.loader import ScenarioLoader, ScenarioLoadError
from core.scheduler import Scheduler
from core.validator import ScheduleValidator

import ui.components.scenario_view as scenario_view
import ui.components.bus_timetable as bus_timetable
import ui.components.station_view as station_view
import ui.components.operator_view as operator_view

# ──────────────────────────────────── Page config ────────────────────────────

st.set_page_config(
    page_title="Bus Charging Scheduler",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ──────────────────────────────────── CSS ────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

html, body, [class*="css"] {
    font-family: 'Space Grotesk', sans-serif;
}
code, .stCode, [data-testid="stCode"] {
    font-family: 'JetBrains Mono', monospace !important;
}

/* App background */
.stApp {
    background: #0F1117;
}
.main .block-container {
    background: #0F1117;
    padding-top: 1.5rem;
    max-width: 1400px;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #1A1D26;
    border-right: 1px solid #2D3142;
}

/* Header */
.app-header {
    background: linear-gradient(135deg, #1A1D26 0%, #0F1117 100%);
    border: 1px solid #2D3142;
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.app-title {
    font-size: 28px;
    font-weight: 800;
    color: #F8FAFC;
    letter-spacing: -0.5px;
    margin: 0;
}
.app-subtitle {
    font-size: 13px;
    color: #94A3B8;
    margin-top: 4px;
}
.status-dot {
    width: 10px; height: 10px;
    background: #22C55E;
    border-radius: 50%;
    display: inline-block;
    margin-right: 6px;
    animation: pulse 2s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    background: #1A1D26;
    padding: 4px;
    border-radius: 8px;
    border: 1px solid #2D3142;
}
.stTabs [data-baseweb="tab"] {
    color: #94A3B8;
    font-weight: 600;
    font-size: 13px;
    border-radius: 6px;
    padding: 8px 16px;
}
.stTabs [aria-selected="true"] {
    background: #2563EB !important;
    color: #FFFFFF !important;
}

/* Metrics */
[data-testid="metric-container"] {
    background: #1A1D26;
    border: 1px solid #2D3142;
    border-radius: 8px;
    padding: 12px 16px;
}
[data-testid="metric-container"] label {
    color: #94A3B8 !important;
    font-size: 11px !important;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    color: #F8FAFC !important;
    font-weight: 700 !important;
    font-size: 20px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    border: 1px solid #2D3142 !important;
    border-radius: 8px !important;
    overflow: hidden;
}
.stDataFrame [data-testid="data-grid-canvas"] {
    background: #1A1D26 !important;
}

/* Selectbox / multiselect */
[data-testid="stSelectbox"], [data-testid="stMultiSelect"] {
    background: #1A1D26;
}
.stSelectbox > div > div, .stMultiSelect > div > div {
    background: #1A1D26 !important;
    border: 1px solid #2D3142 !important;
    color: #F8FAFC !important;
}

/* Divider */
hr {
    border-color: #2D3142 !important;
    margin: 16px 0 !important;
}

/* All text */
h1, h2, h3, h4, h5, h6, p, span, label, div {
    color: #F8FAFC;
}
.stMarkdown p, .stMarkdown span {
    color: #CBD5E1;
}

/* Section headers within markdown */
.stMarkdown h3 {
    color: #F8FAFC;
    font-weight: 700;
    font-size: 18px;
    margin-bottom: 12px;
}

/* Validation errors */
.validation-error {
    background: #450A0A;
    border: 1px solid #EF4444;
    border-radius: 8px;
    padding: 12px 16px;
    color: #FCA5A5;
    font-size: 13px;
    margin-bottom: 8px;
}

/* Info boxes */
.stAlert {
    border-radius: 8px;
}

/* Spinner */
.stSpinner {
    color: #2563EB !important;
}

/* Scenario selector card */
.scenario-card {
    background: #1A1D26;
    border: 1px solid #2D3142;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 16px;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────── Header ─────────────────────────────────

st.markdown("""
<div class="app-header">
  <div>
    <div class="app-title">⚡ Bus Charging Scheduler</div>
    <div class="app-subtitle">
      Event-driven simulation · Weighted multi-objective optimisation · 5 scenarios
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:12px;color:#94A3B8">
      <span class="status-dot"></span>Live
    </div>
    <div style="font-size:11px;color:#64748B;margin-top:2px">
      Bengaluru ↔ Kochi · 540 km · 4 stations
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────── Load scenarios ─────────────────────────

SCENARIOS_DIR = os.path.join(ROOT, "data", "scenarios")

@st.cache_resource
def load_all_scenarios():
    loader = ScenarioLoader(SCENARIOS_DIR)
    configs = {}
    errors = {}
    for fp in loader.list_scenarios():
        try:
            cfg = loader.load(fp)
            configs[cfg.name] = cfg
        except ScenarioLoadError as e:
            errors[os.path.basename(fp)] = str(e)
    return configs, errors

configs, load_errors = load_all_scenarios()

if load_errors:
    for fname, err in load_errors.items():
        st.error(f"Failed to load {fname}: {err}")

if not configs:
    st.error("No scenarios could be loaded. Check the `data/scenarios/` directory.")
    st.stop()

# ──────────────────────────────────── Scenario selector ──────────────────────

col_sel, col_info = st.columns([2, 3])

with col_sel:
    scenario_names = list(configs.keys())
    selected_name = st.selectbox(
        "📂 Select Scenario",
        scenario_names,
        index=0,
        key="scenario_selector",
        help="Choose one of the 5 pre-loaded scenarios"
    )

config = configs[selected_name]

with col_info:
    w = config.weights
    st.markdown(
        f"<div class='scenario-card'>"
        f"<div style='font-size:14px;font-weight:700;color:#F8FAFC'>{config.name}</div>"
        f"<div style='font-size:12px;color:#94A3B8;margin-top:4px'>{config.description}</div>"
        f"<div style='margin-top:8px;font-size:11px;color:#64748B'>"
        f"Weights — Individual: <b style='color:#60A5FA'>{w.individual}</b> · "
        f"Operator: <b style='color:#34D399'>{w.operator}</b> · "
        f"Overall: <b style='color:#F472B6'>{w.overall}</b>"
        f"</div></div>",
        unsafe_allow_html=True
    )

# ──────────────────────────────────── Run scheduler ──────────────────────────

@st.cache_data(ttl=None, show_spinner=False)
def run_scheduler(scenario_id: str, _config):
    """Cache results per scenario ID. Rerun only if scenario changes."""
    scheduler = Scheduler(reassignment_threshold_min=30.0, max_iterations=10)
    result = scheduler.run(_config)

    validator = ScheduleValidator()
    errors = validator.validate(result)
    return result, errors

with st.spinner("Running scheduler..."):
    result, validation_errors = run_scheduler(config.id, config)

# Show validation errors if any
if validation_errors:
    with st.expander(f"⚠️ {len(validation_errors)} validation issue(s)", expanded=True):
        for err in validation_errors:
            st.markdown(f"<div class='validation-error'>🚨 {err}</div>", unsafe_allow_html=True)
else:
    st.success(f"✅ Schedule valid — {len(result.bus_timelines)} buses scheduled, all hard constraints satisfied.")

# ──────────────────────────────────── Tabs ────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📋 Scenario Input",
    "🚌 Per-Bus Timetable",
    "🔌 Per-Station Queue",
    "🏢 Operator Stats",
])

with tab1:
    scenario_view.render(config)

with tab2:
    bus_timetable.render(result)

with tab3:
    station_view.render(result)

with tab4:
    operator_view.render(result)
