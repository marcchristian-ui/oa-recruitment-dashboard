"""Show what the dashboard currently counts as Open / Active for May 2026."""
import pandas as pd

from manatal.client import (
    fetch_all_jobs, fetch_all_organizations, fetch_all_users, refresh_window_key,
)
from manatal.constants import EXCLUDE_HASHES, STATUS_ACTIVE, EXCLUDE_FROM_AGING
from manatal.payload import START_MONTH, _organic_kind
from manatal.transforms import jobs_to_frame, month_window

window_key = refresh_window_key()
df = jobs_to_frame(
    fetch_all_jobs(window_key),
    fetch_all_organizations(window_key),
    fetch_all_users(window_key),
)

# Apply app.py filters
df = df[df["client_name"].str.upper() != "OA"]
df = df[~df["client_name"].str.contains("EVERGREEN", case=False, na=False)]
df = df[~df["position_name"].str.contains("POOLING", case=False, na=False)]
df = df[~df["hash"].isin(EXCLUDE_HASHES)]

window_start = pd.Timestamp(year=START_MONTH[0], month=START_MONTH[1], day=1)
df = df[(df["open_at"] >= window_start) | (df["close_at"].isna()) | (df["close_at"] >= window_start)]

start, end = month_window(2026, 5)

def _was_open_during(r):
    if pd.isna(r["open_at"]) or r["open_at"] >= end:
        return False
    if r["open_at"] >= start:
        return True
    if pd.notna(r.get("som_open_through")):
        return r["som_open_through"] >= start
    eff_close = r["close_at"]
    if pd.notna(r["offer_acceptance_date"]):
        eff_close = (
            min(eff_close, r["offer_acceptance_date"])
            if pd.notna(eff_close)
            else r["offer_acceptance_date"]
        )
    if pd.notna(eff_close):
        return eff_close >= start
    return r["status"] == STATUS_ACTIVE

open_during = df[df.apply(_was_open_during, axis=1)]
currently_active = open_during[open_during["status"] == STATUS_ACTIVE]

def _excluded_from_aging(r) -> bool:
    cl = str(r["client_name"]).upper()
    pos = str(r["position_name"]).upper()
    kind = _organic_kind(r)
    for ec, ep, ek in EXCLUDE_FROM_AGING:
        if ec in cl and ep in pos and (ek is None or ek == kind):
            return True
    return False

if not currently_active.empty:
    currently_active = currently_active[~currently_active.apply(_excluded_from_aging, axis=1)]

currently_active = currently_active.sort_values("open_at")

print("\n=== Dashboard 'Open / Active' for May 2026 ===")
print(f"{'open_at':<12} {'HC':>3} {'hash':<10} {'client':<28} {'role'}")
print("-"*110)
total = 0
for _, r in currently_active.iterrows():
    hc = int(r['headcount']) if pd.notna(r['headcount']) else 1
    total += hc
    print(f"{str(r['open_at'])[:10]:<12} {hc:>3} {r['hash']:<10} {str(r['client_name'])[:28]:<28} {r['position_name']}")
print("-"*110)
print(f"TOTAL roles: {len(currently_active)}   TOTAL HC: {total}")
