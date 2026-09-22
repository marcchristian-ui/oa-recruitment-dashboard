"""Inspect ORGANIKA V6Y9X78R — third hash for same role, appeared since last week."""
from manatal.client import (
    fetch_all_jobs, fetch_all_organizations, fetch_all_users,
    fetch_job_offer_matches, refresh_window_key,
)
from manatal.transforms import jobs_to_frame

window_key = refresh_window_key()
df = jobs_to_frame(
    fetch_all_jobs(window_key),
    fetch_all_organizations(window_key),
    fetch_all_users(window_key),
)

row = df[df["hash"] == "V6Y9X78R"]
if row.empty:
    print("V6Y9X78R NOT FOUND")
else:
    r = row.iloc[0]
    for col in ["hash","id","client_name","position_name","status","headcount",
                "open_at","close_at","offer_acceptance_date","start_date","updated_at","owner_name"]:
        print(f"  {col:<25} {r[col]}")

# Check if V6Y9X78R has any candidates in "Job Offer" pipeline stage
matches = fetch_job_offer_matches(window_key)
print(f"\nTotal job_offer_matches: {len(matches)}")
v6_id = df.loc[df['hash']=='V6Y9X78R','id'].iloc[0] if not row.empty else None
hits = [m for m in matches if (m.get('job',{}).get('id') if isinstance(m.get('job'),dict) else m.get('job')) == v6_id]
print(f"Matches for V6Y9X78R (job_id={v6_id}): {len(hits)}")
for h in hits[:3]:
    print(f"  {h}")
