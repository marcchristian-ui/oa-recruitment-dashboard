#!/usr/bin/env python
"""Pre-build the dashboard payload JSON for Streamlit Cloud.

Streamlit Cloud puts apps to sleep after ~15 min of inactivity. On
cold start the app has to re-fetch all jobs / orgs / users / active
matches from Manatal (30-90 seconds). Pre-building the payload here
and committing it as data/dashboard_payload.json lets the deployed
app skip those API calls entirely — first page load drops to a few
seconds.

Run after every /refresh-dashboard so the cache stays current.
Requires MANATAL_API_TOKEN in .env (same as app.py)."""
import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from manatal.client import (  # noqa: E402
    fetch_all_jobs,
    fetch_all_organizations,
    fetch_all_users,
    fetch_all_active_matches,
    has_credentials,
    refresh_window_key,
)
from manatal.constants import EXCLUDE_HASHES  # noqa: E402
from manatal.payload import build_payload, START_MONTH  # noqa: E402
from manatal.transforms import jobs_to_frame  # noqa: E402


def _unwrap(fn):
    """Peel @st.cache_data so we can call these from a plain CPython script."""
    return getattr(fn, "__wrapped__", fn)


def main() -> int:
    if not has_credentials():
        print("ERROR: MANATAL_API_TOKEN missing. Set it in .env or environment.", file=sys.stderr)
        return 1

    key = refresh_window_key()
    print(f"Window key: {key}")

    jobs = _unwrap(fetch_all_jobs)(key)
    print(f"  fetched {len(jobs)} jobs")
    orgs = _unwrap(fetch_all_organizations)(key)
    print(f"  fetched {len(orgs)} orgs")
    users = _unwrap(fetch_all_users)(key)
    print(f"  fetched {len(users)} users")

    try:
        active_matches = _unwrap(fetch_all_active_matches)(key)
        print(f"  fetched {len(active_matches)} active matches")
    except Exception as e:
        print(f"  WARN active matches scan failed: {e}", file=sys.stderr)
        active_matches = []

    job_offer_matches = [
        m for m in active_matches
        if ((m.get("job_pipeline_stage") or {}).get("name") or "").strip().lower() == "job offer"
    ]

    df = jobs_to_frame(jobs, orgs, users)
    if df.empty:
        print("ERROR: No jobs returned from Manatal", file=sys.stderr)
        return 1

    # Mirror the exclusion filter from app.py exactly.
    df = df[df["client_name"].str.upper() != "OA"]
    df = df[~df["client_name"].str.contains("EVERGREEN", case=False, na=False)]
    df = df[~df["position_name"].str.contains("POOLING", case=False, na=False)]
    df = df[~df["hash"].isin(EXCLUDE_HASHES)]

    window_start = pd.Timestamp(year=START_MONTH[0], month=START_MONTH[1], day=1)
    df = df[
        (df["open_at"] >= window_start)
        | (df["close_at"].isna())
        | (df["close_at"] >= window_start)
    ]
    print(f"  {len(df)} jobs after exclusions")

    payload, months, default_sel = build_payload(df, job_offer_matches, active_matches=active_matches)

    out_path = ROOT / "data" / "dashboard_payload.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "payload": payload,
        "months": months,
        "default_sel": default_sel,
        "_built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "_source": "build_dashboard_payload.py",
    }
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(out, f, default=str, separators=(",", ":"))
    size_kb = out_path.stat().st_size // 1024
    print(f"Wrote {out_path.name} ({size_kb} KB) · default_sel={default_sel} · {len(months)} months")
    return 0


if __name__ == "__main__":
    sys.exit(main())
