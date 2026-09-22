import datetime as dt
import os
import time
from typing import Iterator
from zoneinfo import ZoneInfo
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


def _get_setting(name: str, default: str = "") -> str:
    """Read a config value from Streamlit Cloud secrets first, then env/.env.

    Streamlit Community Cloud stores secrets in ``st.secrets`` (populated from the
    app's Secrets UI). Local development uses ``.env`` via python-dotenv. This
    helper lets the same code path serve both without changes.
    """
    try:
        # ``st.secrets`` raises if secrets.toml is missing on some Streamlit
        # versions, so guard the lookup.
        if name in st.secrets:
            val = st.secrets[name]
            if val:
                return str(val)
    except Exception:
        pass
    return os.getenv(name, default)


API_BASE = _get_setting("MANATAL_API_BASE", "https://api.manatal.com/open/v3").rstrip("/")
API_TOKEN = _get_setting("MANATAL_API_TOKEN", "")

# Manatal data refreshes at two fixed times each day: 10:00 and 18:00 Asia/Manila.
REFRESH_HOURS = (10, 18)
REFRESH_TZ = ZoneInfo("Asia/Manila")
# Cache TTL is a safety net; invalidation is primarily driven by `window_key`.
CACHE_TTL_SECONDS = 24 * 60 * 60
# Legacy export kept so existing imports keep working — interpreted by app.py.
REFRESH_TTL_SECONDS = CACHE_TTL_SECONDS


def _now_manila() -> dt.datetime:
    return dt.datetime.now(REFRESH_TZ)


def refresh_window_key(now: dt.datetime | None = None) -> str:
    """Stable cache key that flips at each scheduled refresh (10:00 / 18:00 Manila)."""
    now = now or _now_manila()
    slot = "00"
    for h in REFRESH_HOURS:
        if now.hour >= h:
            slot = f"{h:02d}"
    return f"{now.date().isoformat()}-{slot}"


def seconds_until_next_refresh(now: dt.datetime | None = None) -> int:
    """Seconds remaining until the next scheduled refresh time (Manila)."""
    now = now or _now_manila()
    candidates: list[dt.datetime] = []
    for h in REFRESH_HOURS:
        cand = now.replace(hour=h, minute=0, second=0, microsecond=0)
        if cand > now:
            candidates.append(cand)
    if not candidates:
        # Past today's last refresh — next one is tomorrow's first.
        candidates.append(
            (now + dt.timedelta(days=1)).replace(
                hour=REFRESH_HOURS[0], minute=0, second=0, microsecond=0
            )
        )
    nxt = min(candidates)
    return max(60, int((nxt - now).total_seconds()))


def _headers() -> dict:
    if not API_TOKEN:
        raise RuntimeError("MANATAL_API_TOKEN missing. Add it to .env in the project root.")
    return {"Authorization": f"Token {API_TOKEN}", "Accept": "application/json"}


def _paginate(endpoint: str, params: dict | None = None, *, page_size: int = 100, max_attempts: int = 6) -> Iterator[dict]:
    url = f"{API_BASE}/{endpoint.strip('/')}/"
    params = dict(params or {})
    params.setdefault("page_size", page_size)
    while url:
        last_err: Exception | None = None
        r = None
        for attempt in range(max_attempts):
            try:
                r = requests.get(url, headers=_headers(), params=params, timeout=60)
                if r.status_code == 429:
                    time.sleep(min(30, 2 ** attempt))
                    continue
                r.raise_for_status()
                break
            except requests.RequestException as e:
                last_err = e
                if attempt == max_attempts - 1:
                    raise
                # Exponential backoff capped at 30s (covers transient drops)
                time.sleep(min(30, 2 ** attempt))
        if r is None:
            if last_err:
                raise last_err
            return
        data = r.json()
        for item in data.get("results", []):
            yield item
        url = data.get("next")
        params = None  # next URL already has them


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading jobs from Manatal…")
def fetch_all_jobs(window_key: str = "") -> list[dict]:
    return list(_paginate("jobs"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading organizations…")
def fetch_all_organizations(window_key: str = "") -> list[dict]:
    return list(_paginate("organizations"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading Manatal users…")
def fetch_all_users(window_key: str = "") -> list[dict]:
    """Manatal users (recruiters). Used to map owner_id -> display name."""
    return list(_paginate("users"))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Loading recent matches…")
def fetch_recent_matches(window_key: str = "", months_back: int = 6) -> list[dict]:
    since = (dt.datetime.utcnow() - dt.timedelta(days=30 * months_back)).strftime(
        "%Y-%m-%dT00:00:00Z"
    )
    return list(_paginate("matches", {"updated_at__gte": since}))


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Scanning candidate pipeline…")
def fetch_all_active_matches(window_key: str = "", months_back: int = 2) -> list[dict]:
    """All ACTIVE candidate-job matches, regardless of pipeline stage.
    Used by the Recruiter View to count candidates per stage per recruiter.
    Limited to the last `months_back` months (default 2) to keep the response
    small. Fails soft: returns whatever was fetched so far if the API errors
    mid-scan, so the rest of the dashboard still loads."""
    since = (dt.datetime.utcnow() - dt.timedelta(days=30 * months_back)).strftime(
        "%Y-%m-%dT00:00:00Z"
    )
    out: list[dict] = []
    try:
        for m in _paginate("matches", {"updated_at__gte": since}, page_size=50):
            if m.get("is_active"):
                out.append(m)
    except Exception as e:  # noqa: BLE001
        # Don't crash the dashboard if matches scan fails — return partial results.
        import logging
        logging.warning(f"fetch_all_active_matches partial failure: {e!r}")
    return out


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner="Scanning Job Offer pipeline…")
def fetch_job_offer_matches(window_key: str = "", months_back: int = 6) -> list[dict]:
    """Active matches currently sitting in the 'Job Offer' pipeline stage.
    Used to auto-populate the For Job Offer KPI without manual hash entries.
    Limited to matches updated in the last `months_back` months for efficiency."""
    since = (dt.datetime.utcnow() - dt.timedelta(days=30 * months_back)).strftime(
        "%Y-%m-%dT00:00:00Z"
    )
    out = []
    for m in _paginate("matches", {"updated_at__gte": since}):
        if not m.get("is_active"):
            continue
        ps = (m.get("job_pipeline_stage") or {}).get("name") or ""
        if ps.strip().lower() == "job offer":
            out.append(m)
    return out


def has_credentials() -> bool:
    return bool(API_TOKEN)
