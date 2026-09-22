import base64
import json
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from manatal.client import (
    fetch_all_jobs,
    fetch_all_organizations,
    fetch_all_users,
    fetch_all_active_matches,
    fetch_job_offer_matches,
    has_credentials,
    refresh_window_key,
    seconds_until_next_refresh,
)
from manatal.payload import build_payload, START_MONTH
from manatal.transforms import jobs_to_frame

st.set_page_config(
    page_title="Recruitment Dashboard — Outsource Accelerator",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Strip Streamlit's chrome so the embedded dashboard fills the viewport.
st.markdown(
    """
    <style>
      [data-testid="stHeader"], [data-testid="stToolbar"], footer, #MainMenu {display:none !important;}
      .block-container {padding:0 !important; max-width:100% !important;}
      [data-testid="stAppViewContainer"] {background:#f0f2f5;}
      [data-testid="stAppViewBlockContainer"] {padding:0 !important;}
      iframe {border:none !important;}
    </style>
    """,
    unsafe_allow_html=True,
)

# Refresh data at 10:00 and 18:00 local time. seconds_until_next_refresh()
# returns the gap to the next scheduled trigger; st_autorefresh fires once at
# that moment, after which the app reruns and recomputes the next gap.
st_autorefresh(interval=seconds_until_next_refresh() * 1000, key="manatal_refresh")

if not has_credentials():
    st.error("MANATAL_API_TOKEN missing. Add it to .env and rerun.")
    st.stop()

window_key = refresh_window_key()
with st.spinner("Loading Manatal data…"):
    try:
        jobs = fetch_all_jobs(window_key)
        orgs = fetch_all_organizations(window_key)
        users = fetch_all_users(window_key)
    except Exception as e:
        st.error(f"Manatal API error (jobs/orgs/users): {e}")
        st.stop()

# Matches scan is optional — if it fails, candidate pipeline section just stays empty.
try:
    active_matches = fetch_all_active_matches(window_key)
except Exception as e:
    st.warning(f"Candidate pipeline scan failed ({type(e).__name__}); continuing without it. Refresh later if you want it populated.")
    active_matches = []
job_offer_matches = [
    m for m in active_matches
    if ((m.get("job_pipeline_stage") or {}).get("name") or "").strip().lower() == "job offer"
]

df = jobs_to_frame(jobs, orgs, users)
if df.empty:
    st.warning("No jobs returned from Manatal.")
    st.stop()

# Exclude OA (Outsource Accelerator) internal roles from all counts.
df = df[df["client_name"].str.upper() != "OA"]

# Exclude EVERGREEN REQUISITION (talent-pool placeholder, not real client work).
df = df[~df["client_name"].str.contains("EVERGREEN", case=False, na=False)]

# Exclude pooling roles (sourcing pools, not actual hiring needs).
df = df[~df["position_name"].str.contains("POOLING", case=False, na=False)]

# Exclude specific job hashes (per user — not part of the dashboard scope).
from manatal.constants import EXCLUDE_HASHES
df = df[~df["hash"].isin(EXCLUDE_HASHES)]

# Restrict to roles that touch the Nov 2025 → present window.
window_start = pd.Timestamp(year=START_MONTH[0], month=START_MONTH[1], day=1)
df = df[
    (df["open_at"] >= window_start)
    | (df["close_at"].isna())
    | (df["close_at"] >= window_start)
]

payload, months, default_sel = build_payload(df, job_offer_matches, active_matches=active_matches)

template_path = Path(__file__).parent / "templates" / "dashboard.html"
template = template_path.read_text(encoding="utf-8")

# Optional brand logo: drop a file named oa-logo.png / .svg / .jpg / .jpeg in the
# templates/ folder and it will replace the inline SVG approximation.
def _logo_data_uri() -> str:
    tdir = template_path.parent
    for ext, mime in (("png", "image/png"), ("svg", "image/svg+xml"),
                      ("jpg", "image/jpeg"), ("jpeg", "image/jpeg")):
        p = tdir / f"oa-logo.{ext}"
        if p.exists():
            b64 = base64.b64encode(p.read_bytes()).decode("ascii")
            return f"data:{mime};base64,{b64}"
    return ""

html = (
    template
    .replace("__DATA_JSON__", json.dumps(payload))
    .replace("__MONTHS__", json.dumps(months))
    .replace("__SEL__", json.dumps(default_sel))
    .replace("__LOGO_DATA_URI__", _logo_data_uri())
)

components.html(html, height=2400, scrolling=True)
