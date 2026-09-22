"""Diagnostic: dump the exact list of roles the dashboard counts as
   Start-of-Month for May 2026, so we can compare to the user's
   source-of-truth list of 13 rows / 15 HC."""
import pandas as pd

from manatal.client import (
    fetch_all_jobs,
    fetch_all_organizations,
    fetch_all_users,
    refresh_window_key,
)
from manatal.constants import EXCLUDE_HASHES
from manatal.payload import START_MONTH
from manatal.transforms import jobs_to_frame, month_window

window_key = refresh_window_key()
jobs = fetch_all_jobs(window_key)
orgs = fetch_all_organizations(window_key)
users = fetch_all_users(window_key)

df = jobs_to_frame(jobs, orgs, users)

# Apply the same filters as app.py
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

# Replicate _was_open_during for May 2026
from manatal.constants import STATUS_ACTIVE
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
som_df = open_during[open_during["open_at"] < start]
som_df = som_df.sort_values("open_at")

print(f"\nMay 2026 Start-of-Month — roles counted by dashboard")
print(f"{'='*110}")
print(f"{'open_at':<12} {'HC':>3} {'hash':<10} {'status':<10} {'client':<28} {'role'}")
print(f"{'-'*110}")
total_hc = 0
for _, r in som_df.iterrows():
    hc = int(r['headcount']) if pd.notna(r['headcount']) else 1
    total_hc += hc
    print(f"{str(r['open_at'])[:10]:<12} {hc:>3} {r['hash']:<10} {str(r['status']):<10} {str(r['client_name'])[:28]:<28} {r['position_name']}")
print(f"{'-'*110}")
print(f"TOTAL roles: {len(som_df)}   TOTAL HC: {total_hc}")
