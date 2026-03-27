"""
dashboard.py — Autonomous Chaos Engineering & Self-Healing Platform
Real-time SRE Dashboard (Streamlit + Plotly)
 
Features:
  • Cluster Heartbeat — live multi-metric time-series
  • Threat Level — animated Plotly gauge
  • Chaos Control Panel — one-click fault injection
  • Autonomous Action Log — live self-healing event stream
"""
 
from __future__ import annotations
 
import json
import logging
import random
import time
from datetime import datetime, timezone
from typing import Any
 
import httpx
import plotly.graph_objects as go
import streamlit as st
 
# ---------------------------------------------------------------------------
# Page config (MUST be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Chaos SRE Platform",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)
 
# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("chaos.dashboard")
 
# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ML_BACKEND_URL = "http://ml_backend:8000"  # override via env / sidebar
CHAOS_API_URL = "http://chaos_operator:9000"  # Person A's endpoint
MAX_HISTORY = 120  # data points retained in session
REFRESH_INTERVAL_S = 1
 
# ---------------------------------------------------------------------------
# Custom CSS — Dark Mode SRE aesthetic
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Syne:wght@400;700;800&display=swap');
 
:root {
    --bg-primary:    #080c14;
    --bg-card:       #0d1421;
    --bg-card2:      #111827;
    --border:        #1e2d45;
    --accent-cyan:   #00e5ff;
    --accent-amber:  #ffab00;
    --accent-red:    #ff3d5a;
    --accent-green:  #00e676;
    --accent-purple: #7c4dff;
    --text-primary:  #e2e8f0;
    --text-dim:      #64748b;
    --font-mono:     'JetBrains Mono', monospace;
    --font-display:  'Syne', sans-serif;
}
 
html, body, [class*="css"] {
    font-family: var(--font-mono) !important;
    background-color: var(--bg-primary) !important;
    color: var(--text-primary) !important;
}
 
/* Hide default Streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1rem 2rem 2rem 2rem !important; max-width: 100% !important; }
 
/* ── Header bar ── */
.sre-header {
    background: linear-gradient(135deg, #0d1421 0%, #111827 50%, #0a1628 100%);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.2rem 2rem;
    margin-bottom: 1.5rem;
    display: flex;
    align-items: center;
    gap: 1.5rem;
    box-shadow: 0 0 40px rgba(0,229,255,0.06);
}
.sre-header .logo { font-family: var(--font-display); font-size: 1.6rem; font-weight: 800;
    background: linear-gradient(90deg, var(--accent-cyan), var(--accent-purple));
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.sre-header .subtitle { font-size: 0.7rem; color: var(--text-dim); letter-spacing: 0.15em; text-transform: uppercase; margin-top: 0.15rem; }
.live-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent-green);
    box-shadow: 0 0 12px var(--accent-green); animation: pulse 1.4s ease-in-out infinite; display: inline-block; margin-right: 6px; }
@keyframes pulse { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:0.5;transform:scale(1.3)} }
 
/* ── KPI cards ── */
.kpi-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    text-align: center;
    position: relative;
    overflow: hidden;
    transition: border-color 0.3s;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; height: 2px;
}
.kpi-card.cyan::before  { background: var(--accent-cyan); }
.kpi-card.amber::before { background: var(--accent-amber); }
.kpi-card.red::before   { background: var(--accent-red); }
.kpi-card.green::before { background: var(--accent-green); }
.kpi-label { font-size: 0.6rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 0.4rem; }
.kpi-value { font-family: var(--font-display); font-size: 2rem; font-weight: 800; line-height: 1; }
.kpi-unit  { font-size: 0.65rem; color: var(--text-dim); margin-top: 0.2rem; }
 
/* ── Section headings ── */
.section-title {
    font-family: var(--font-display);
    font-size: 0.75rem;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--text-dim);
    padding: 0 0 0.5rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 1rem;
}
 
/* ── Chaos buttons ── */
.stButton > button {
    font-family: var(--font-mono) !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    background: var(--bg-card2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 8px !important;
    color: var(--text-primary) !important;
    padding: 0.55rem 0.8rem !important;
    width: 100% !important;
    transition: all 0.2s !important;
    letter-spacing: 0.05em;
    text-align: left !important;
}
.stButton > button:hover {
    border-color: var(--accent-amber) !important;
    color: var(--accent-amber) !important;
    box-shadow: 0 0 16px rgba(255,171,0,0.15) !important;
}
 
/* ── Action log ── */
.action-log {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 1rem;
    height: 320px;
    overflow-y: auto;
    font-size: 0.72rem;
    line-height: 1.7;
}
.action-log::-webkit-scrollbar { width: 4px; }
.action-log::-webkit-scrollbar-track { background: var(--bg-card); }
.action-log::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.log-entry { padding: 0.25rem 0; border-bottom: 1px solid rgba(30,45,69,0.5); }
.log-time  { color: var(--text-dim); }
.log-ok    { color: var(--accent-green); }
.log-warn  { color: var(--accent-amber); }
.log-crit  { color: var(--accent-red); }
.log-info  { color: var(--accent-cyan); }
 
/* ── Status badge ── */
.badge {
    display: inline-block;
    padding: 0.15rem 0.55rem;
    border-radius: 4px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
}
.badge-ok   { background: rgba(0,230,118,0.12); color: var(--accent-green); border: 1px solid rgba(0,230,118,0.3); }
.badge-warn { background: rgba(255,171,0,0.12);  color: var(--accent-amber); border: 1px solid rgba(255,171,0,0.3); }
.badge-crit { background: rgba(255,61,90,0.12);  color: var(--accent-red);   border: 1px solid rgba(255,61,90,0.3); }
 
/* Sidebar */
[data-testid="stSidebar"] {
    background: var(--bg-card) !important;
    border-right: 1px solid var(--border) !important;
}
[data-testid="stSidebar"] * { font-family: var(--font-mono) !important; }
</style>
"""
 
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
 