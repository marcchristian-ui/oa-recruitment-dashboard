import base64
import datetime as dt
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

# Pre-built payload path. If present and fresh, the deployed app skips the
# live Manatal fetches entirely (which take 30-90s on a cold-started
# Streamlit Cloud container). Rebuilt by scripts/build_dashboard_payload.py
# as part of /refresh-dashboard.
PAYLOAD_CACHE_PATH = Path(__file__).parent / "data" / "dashboard_payload.json"
PAYLOAD_CACHE_MAX_AGE_HOURS = 48


@st.cache_data(ttl=600, show_spinner=False)
def _load_cached_payload(mtime_key: float):
    """Return (payload, months, default_sel, built_at_iso) from the pre-built JSON,
    or None if missing. mtime_key busts Streamlit's cache when the file is rewritten
    (locally or via a fresh Streamlit Cloud deploy)."""
    if not PAYLOAD_CACHE_PATH.exists():
        return None
    try:
        with PAYLOAD_CACHE_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data["payload"], data["months"], data["default_sel"], data.get("_built_at", "")
    except Exception:
        return None


def _cached_payload_or_none():
    """Return (payload, months, default_sel) if the pre-built JSON is present and
    its _built_at is within PAYLOAD_CACHE_MAX_AGE_HOURS; else None.

    Uses the embedded _built_at timestamp rather than file mtime because Streamlit
    Cloud resets mtime to the git-clone time on each deploy, which would otherwise
    make the cache look always-fresh regardless of how old the data really is."""
    if not PAYLOAD_CACHE_PATH.exists():
        return None
    loaded = _load_cached_payload(PAYLOAD_CACHE_PATH.stat().st_mtime)
    if loaded is None:
        return None
    payload, months, default_sel, built_at_iso = loaded
    if built_at_iso:
        try:
            built_at = dt.datetime.fromisoformat(built_at_iso.replace("Z", "+00:00"))
            if built_at.tzinfo is None:
                built_at = built_at.replace(tzinfo=dt.timezone.utc)
            age_hours = (dt.datetime.now(dt.timezone.utc) - built_at).total_seconds() / 3600
            if age_hours > PAYLOAD_CACHE_MAX_AGE_HOURS:
                return None
        except Exception:
            # If the timestamp is unparseable, trust the file rather than refuse to render.
            pass
    return payload, months, default_sel

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

# Fast path: serve the pre-built payload if it's present and fresh. On Streamlit
# Cloud this takes the first-paint from 30-90s (cold-start + 4 Manatal API round
# trips) down to a few seconds (static JSON read).
cached = _cached_payload_or_none()
if cached is not None:
    payload, months, default_sel = cached
else:
    # Fallback: live Manatal fetch. Used for local development and as a safety
    # net if the pre-built payload is missing / older than 48h.
    if not has_credentials():
        st.error(
            "MANATAL_API_TOKEN missing and no fresh data/dashboard_payload.json. "
            "Run `python scripts/build_dashboard_payload.py` locally first, "
            "or add MANATAL_API_TOKEN to .env / Streamlit secrets."
        )
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
