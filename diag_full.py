"""End-to-end check: run build_payload for May 2026 and print the key KPIs."""
import pandas as pd

from manatal.client import (
    fetch_all_jobs, fetch_all_organizations, fetch_all_users,
    fetch_job_offer_matches, refresh_window_key,
)
from manatal.constants import EXCLUDE_HASHES
from manatal.payload import START_MONTH, build_payload
from manatal.transforms import jobs_to_frame

window_key = refresh_window_key()
df = jobs_to_frame(
    fetch_all_jobs(window_key),
    fetch_all_organizations(window_key),
    fetch_all_users(window_key),
)
df = df[df["client_name"].str.upper() != "OA"]
df = df[~df["client_name"].str.contains("EVERGREEN", case=False, na=False)]
df = df[~df["position_name"].str.contains("POOLING", case=False, na=False)]
df = df[~df["hash"].isin(EXCLUDE_HASHES)]
window_start = pd.Timestamp(year=START_MONTH[0], month=START_MONTH[1], day=1)
df = df[(df["open_at"] >= window_start) | (df["close_at"].isna()) | (df["close_at"] >= window_start)]

matches = fetch_job_offer_matches(window_key)
payload, months, default_sel = build_payload(df, matches)

print(f"Selected month: {default_sel}")
may = payload["allMonths"]["2026-05"]
print(f"\n=== May 2026 KPIs ===")
print(f"  Start-of-Month (HC):        {may['startOfMonth']}    (roles: {may['startOfMonthRoles']})")
print(f"  Additional in Month (HC):   {may['additionalInMonth']}    (roles: {may['additionalInMonthRoles']})")
print(f"  Pipeline.open (Open KPI):   {may['pipeline']['open']}")
print(f"  Pipeline.forJobOffer:       {may['pipeline']['forJobOffer']}")
print(f"  Pipeline.offerAccepted:     {may['pipeline']['offerAccepted']}")
print(f"  Pipeline.started:           {may['pipeline']['started']}")
print(f"  Pipeline.paused:            {may['pipeline']['paused']}")
print(f"  activeRequisitions:         {may.get('activeRequisitions')}")

print(f"\n=== May Closed Won detail ===")
for cw in may["closedWon"]:
    print(f"  [{cw['stage']}] {cw['client']:<30} {cw['role']:<45} hc={cw['headcount']}")

print(f"\n=== May For Job Offer detail ===")
for io in may.get("inOfferRoles", []):
    print(f"  {io['client']:<30} {io['role']:<45} hc={io['headcount']}")

print(f"\n=== May SoM Carry-Over detail ===")
for s in may.get("somCarryOver", []):
    print(f"  {s['opened'][:10]} {s['client']:<30} {s['role']:<45} hc={s['headcount']} status={s['status']}")
