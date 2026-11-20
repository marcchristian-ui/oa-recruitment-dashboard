# OA Recruitment Dashboard — Handover

Full handover document lives in the OA vault:
**`Documents\Obsidian Vault\RecruitmentVault\08-Playbooks\Recruitment-Dashboard\Handover-v1.md`**

Shortcut to the essentials below. For the full doc — data flow diagram, gotchas,
troubleshooting playbook, change log — read the vault version.

---

## Live URL
Streamlit Cloud deployment auto-deploys from `origin/main` on this repo.

## What this is
Live single-pane view of every active requisition: stage, aging, candidate
pipeline, team & recruiter funnel conversion, monthly KPIs vs
`5% × operational-HC` target. Primary data source: Manatal (ATS) via MCP.

## Refresh commands

| Skill | Writes | Cadence |
|---|---|---|
| `/refresh-dashboard` | All four — candidate funnel, team metrics, recruiter funnel, nurture — in one pass, rebuilds payload, pushes. | On demand |
| `/update-dashboard` | `candidate_funnel_override.json`, current snapshot | 5× daily PHT |
| `/update-recruitment-metrics` | `recruitment_metrics.json` | 2× daily PHT |
| `/update-nurture-list` | `nurture_list.json` | Daily 08:07 PHT |

## Repo layout

```
app.py                              Streamlit entry
templates/dashboard.html            UI (tabs, tiles, charts in inline JS)
manatal/                            Manatal MCP client + payload builder
scripts/build_dashboard_payload.py  Pre-builds the merged JSON Streamlit serves
snapshots/YYYY-MM.json              Per-month pipeline state (committed)
data/candidate_funnel_override.json Current-month funnel names
data/recruitment_metrics.json       Team YTD funnel
data/recruiter_metrics.json         Per-recruiter YTD
data/nurture_list.json              Nurture pipeline
data/dashboard_payload.json         What Streamlit actually reads
```

## Must-know gotchas

1. **Pre-build the payload after every data change.** `scripts/build_dashboard_payload.py`.
2. **`candidates_read.custom_fields` is empty for most candidates.** Manatal's Employee Details tab (incl. Start Date) is not exposed by the Open API — parse Read.AI notes instead.
3. **`stage__in` without `job_id` returns ~13k rows.** Always narrow by `job_id`.
4. **`jobs_list hash__in` is silently ignored.** Use `jobs_read(id=X)` or in-memory filter.
5. **ADAUGEO org id is 637786/639129**, NOT 599280 (which is OA internal — excluded).
6. **Rank-5 event date rule**: `offer_at else hired_at else updated_at`.
7. **Owner IDs**: Alan 99045 / Louie 105855 / Iyah 1242516 / Joberth 237798 / Mark 306203 / Khamz 93938 / Ellie 225662+89009 → Other.

## Monthly target formula
`monthlyTarget = ceil(5% × operational HC at start of month)` — set on each snapshot via `operationalHcStart` + `targetFormula` + `monthlyTarget`.

## Running locally

```powershell
cd "C:\Users\Chris Gaor\recruitment-dashboard"
streamlit run app.py --server.headless=true
# → http://localhost:8501
```

## Owner
Marc Christian (Chris) — `marc.christian@outsourceaccelerator.com`
