# OA Recruitment Dashboard

Streamlit dashboard for Outsource Accelerator's recruitment operations — pulls
live data from the Manatal ATS API and the Nurture List Google Sheet, and
renders monthly funnels, TTF trends, per-recruiter metrics, and role-level
pipeline views.

## Runtime

- **Local:** `streamlit run app.py` after populating `.env` with `MANATAL_API_TOKEN`.
- **Cloud:** deployed on [Streamlit Community Cloud](https://share.streamlit.io/)
  from this repo. Configure `MANATAL_API_TOKEN` in the app's Secrets UI.

## Data flow

| Source | Where it lives | Refresh |
|---|---|---|
| Manatal API (live) | `manatal/client.py` fetches on each app load | Cached until next scheduled refresh (10:00 / 18:00 Manila) |
| Snapshots | `snapshots/YYYY-MM.json` (committed) | Written by the `/update-dashboard` skill on the local runner, pushed to git |
| Candidate funnel override | `data/candidate_funnel_override.json` | Same |
| Recruitment metrics | `data/recruitment_metrics.json` | Written by `/update-recruitment-metrics` (2× daily) |
| Nurture List | `data/nurture_list.json` | Written by `/update-nurture-list` (1× daily) |
| Recruiter metrics | `data/recruiter_metrics.json` | Written when recruiter attribution refresh runs |

Data JSON files are committed so Streamlit Cloud can read them; the local
runner does `git add data/ snapshots/ && git commit && git push` after each
refresh so the cloud dashboard stays current.

## Secrets

`.env` (local) and Streamlit Cloud's Secrets UI both take the same keys:

```
MANATAL_API_TOKEN = "..."
MANATAL_API_BASE  = "https://api.manatal.com/open/v3"   # optional
```

See `.streamlit/secrets.toml.example` for the exact format.

## Repo layout

```
app.py                        # Streamlit entry point
manatal/                      # Manatal API client + payload builders
templates/dashboard.html      # The single-page dashboard rendered via components.html
tabs/                         # Legacy per-tab Streamlit renderers (kept for reference)
data/                         # JSON files consumed by the dashboard
snapshots/                    # Monthly snapshots (source of truth for role-level metrics)
scripts/                      # Local runner scripts (watchdog, tunnels) — mostly gitignored
```

## Access

The app is deployed as a **private** Streamlit Cloud app; viewer access is
gated by an email allowlist configured in the app settings.
