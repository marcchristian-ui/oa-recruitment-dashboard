"""Inspect YEEZY Jr CSR (V6YXVRY8) — user wants it in May Offer Accepted."""
import pandas as pd

from manatal.client import (
    fetch_all_jobs,
    fetch_all_organizations,
    fetch_all_users,
    refresh_window_key,
)
from manatal.transforms import jobs_to_frame

window_key = refresh_window_key()
df = jobs_to_frame(
    fetch_all_jobs(window_key),
    fetch_all_organizations(window_key),
    fetch_all_users(window_key),
)

row = df[df["hash"] == "V6YXVRY8"]
if row.empty:
    print("Hash V6YXVRY8 NOT FOUND in df.")
else:
    r = row.iloc[0]
    for col in [
        "hash", "client_name", "position_name", "status", "headcount",
        "open_at", "close_at", "offer_acceptance_date", "start_date",
        "som_open_through", "updated_at", "owner_name", "role_type",
    ]:
        if col in r.index:
            print(f"{col:<25} {r[col]}")

print("\n--- All YEEZY Jr CSR roles in df ---")
mask = df["client_name"].str.contains("YEEZY", case=False, na=False) & \
       df["position_name"].str.contains("JUNIOR|JR", case=False, na=False)
for _, r in df[mask].iterrows():
    print(f"hash={r['hash']} status={r['status']} open={r['open_at']} close={r['close_at']} offer_acc={r['offer_acceptance_date']} start={r['start_date']} hc={r['headcount']}")
