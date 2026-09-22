"""Check (1) YEEZY V6YXVRY8 in May Closed Won and (2) ORGANIKA 63VX8VVR raw data."""
import pandas as pd

from manatal.client import (
    fetch_all_jobs, fetch_all_organizations, fetch_all_users, refresh_window_key,
)
from manatal.constants import EXCLUDE_HASHES
from manatal.payload import START_MONTH
from manatal.transforms import jobs_to_frame, month_window, in_window

window_key = refresh_window_key()
df_raw = jobs_to_frame(
    fetch_all_jobs(window_key),
    fetch_all_organizations(window_key),
    fetch_all_users(window_key),
)

print("=== (1) ORGANIKA 63VX8VVR raw data (no excludes) ===")
row = df_raw[df_raw["hash"] == "63VX8VVR"]
if row.empty:
    print("NOT FOUND")
else:
    r = row.iloc[0]
    for col in ["hash","client_name","position_name","status","headcount",
                "open_at","close_at","offer_acceptance_date","start_date","updated_at"]:
        print(f"  {col:<25} {r[col]}")

print("\n=== (2) YEEZY V6YXVRY8 — does it land in May Closed Won (Offer Accepted)? ===")
# Apply same filters as app.py
df = df_raw[df_raw["client_name"].str.upper() != "OA"]
df = df[~df["client_name"].str.contains("EVERGREEN", case=False, na=False)]
df = df[~df["position_name"].str.contains("POOLING", case=False, na=False)]
df = df[~df["hash"].isin(EXCLUDE_HASHES)]
window_start = pd.Timestamp(year=START_MONTH[0], month=START_MONTH[1], day=1)
df = df[(df["open_at"] >= window_start) | (df["close_at"].isna()) | (df["close_at"] >= window_start)]

start, end = month_window(2026, 5)
today = pd.Timestamp.now()
closed_pool = df[df.apply(lambda r: in_window(r["offer_acceptance_date"], start, end), axis=1)]
started_df = closed_pool[closed_pool["start_date"].notna() & (closed_pool["start_date"] <= today)]
accepted_df = closed_pool[~closed_pool["id"].isin(started_df["id"])]

print(f"  May closed_pool size: {len(closed_pool)}, started: {len(started_df)}, accepted: {len(accepted_df)}")
print(f"  V6YXVRY8 in closed_pool? {(closed_pool['hash'] == 'V6YXVRY8').any()}")
print(f"  V6YXVRY8 in started_df? {(started_df['hash'] == 'V6YXVRY8').any()}")
print(f"  V6YXVRY8 in accepted_df? {(accepted_df['hash'] == 'V6YXVRY8').any()}")
print(f"  today = {today}")

print("\n=== May Offer Accepted roles (what dashboard shows) ===")
for _, r in accepted_df.iterrows():
    print(f"  {r['hash']} hc={int(r['headcount']) if pd.notna(r['headcount']) else 1} {r['client_name']} | {r['position_name']} | offer_acc={r['offer_acceptance_date']} start={r['start_date']}")

print("\n=== May Started roles ===")
for _, r in started_df.iterrows():
    print(f"  {r['hash']} hc={int(r['headcount']) if pd.notna(r['headcount']) else 1} {r['client_name']} | {r['position_name']} | offer_acc={r['offer_acceptance_date']} start={r['start_date']}")
