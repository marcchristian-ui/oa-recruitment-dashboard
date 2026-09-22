import datetime as dt
from collections import defaultdict
import json
import math
from pathlib import Path

import pandas as pd

from .constants import STATUS_ACTIVE, STATUS_WON, STATUS_LOST, STATUS_ON_HOLD, LOCKED_MONTHS, IN_OFFER_HASHES, ONGOING_CONTRACT_HASHES, CLOSED_WON_VIRTUAL_HASHES, EXCLUDE_IN_OFFER, EXCLUDE_FROM_AGING, AGING_HC_REDUCTION, RECRUITERS, RECRUITER_OVERRIDES  # noqa
from .transforms import month_window, in_window, is_open_at, extract_pause_reason

START_MONTH = (2025, 11)
SNAPSHOT_DIR = Path(__file__).parent.parent / "snapshots"


def _snapshot_path(month_key: str) -> Path:
    return SNAPSHOT_DIR / f"{month_key}.json"


def _load_snapshot(month_key: str) -> dict | None:
    p = _snapshot_path(month_key)
    if p.exists():
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _save_snapshot(month_key: str, data: dict) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    with _snapshot_path(month_key).open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def _safe_int(x) -> int:
    try:
        if pd.isna(x):
            return 0
    except (TypeError, ValueError):
        pass
    try:
        return int(x)
    except (TypeError, ValueError):
        return 0


def _iso_date(ts) -> str:
    if pd.isna(ts):
        return ""
    return pd.Timestamp(ts).strftime("%Y-%m-%d")


def _organic_kind(row) -> str:
    if row["role_type"] == "New Logo":
        return "New Logo"
    return row["organic_subtype"] or "Ramp"


def available_months(today: dt.date | None = None) -> list[dict]:
    today = today or dt.date.today()
    months = []
    y, m = START_MONTH
    while (y, m) <= (today.year, today.month):
        months.append({"value": f"{y}-{m:02d}", "label": dt.date(y, m, 1).strftime("%B %Y")})
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return months


def _job_brief(row, ref_now: pd.Timestamp) -> dict:
    days = _age_in_days(row, ref_now)
    return {
        "role": row["position_name"],
        "client": row["client_name"],
        "type": _organic_kind(row),
        "opened": _iso_date(row["open_at"]),
        "days": days,
        "headcount": _safe_int(row["headcount"]),
    }


def _age_in_days(row, ref_now: pd.Timestamp) -> int:
    """Days a role was/has been open. Stops at offer_acceptance_date once set."""
    if pd.isna(row["open_at"]):
        return 0
    end_dt = row["offer_acceptance_date"] if pd.notna(row["offer_acceptance_date"]) else ref_now
    return max(0, (end_dt - row["open_at"]).days)


def _aging_bucket_counts(open_df: pd.DataFrame, ref_now: pd.Timestamp) -> dict:
    """Headcount sums per aging bucket. Buckets: 0-14, 15-30, 31-45, 46+ days.
    Aging stops at offer_acceptance_date when set."""
    if open_df.empty:
        return {"fresh": 0, "normal": 0, "aging": 0, "critical": 0}
    days = open_df.apply(lambda r: _age_in_days(r, ref_now), axis=1)
    hc = open_df["headcount"].fillna(1)
    return {
        "fresh": int(hc[days <= 14].sum()),
        "normal": int(hc[(days > 14) & (days <= 30)].sum()),
        "aging": int(hc[(days > 30) & (days <= 45)].sum()),
        "critical": int(hc[days > 45].sum()),
    }


def _avg_days(sub: pd.DataFrame, ref_now: pd.Timestamp) -> int:
    if sub.empty:
        return 0
    days = sub.apply(lambda r: _age_in_days(r, ref_now), axis=1)
    return int(days.mean())


def _empty_month_payload() -> dict:
    """Zero-filled payload — used when a per-recruiter view has no jobs."""
    return {
        "totalOpen": 0,
        "startOfMonth": 0,
        "startOfMonthRoles": 0,
        "additionalInMonth": 0,
        "additionalInMonthRoles": 0,
        "monthlyTarget": 0,
        "pipeline": {
            "open": 0, "forJobOffer": 0, "ongoingContract": 0,
            "offerAccepted": 0, "started": 0, "paused": 0,
        },
        "pausedRoles": [],
        "closedLostRoles": [],
        "closedWon": [],
        "inOfferRoles": [],
        "ongoingContractRoles": [],
        "somCarryOver": [],
        "business": {
            "newLogoCount": 0, "rampCount": 0, "backfillCount": 0,
            "newLogoJobs": [], "rampJobs": [], "backfillJobs": [],
        },
        "aging": {
            "avgNewLogo": 0, "avgRamp": 0, "avgBackfill": 0,
            "fresh": 0, "normal": 0, "aging": 0, "critical": 0, "jobs": [],
        },
        "avgTimeToHire": 0,
        "avgTimeToFill": 0,
        "activeRequisitions": 0,
        "activeRequisitionsRoles": 0,
    }


def _build_month(df: pd.DataFrame, year: int, month: int, auto_in_offer: dict[str, int] | None = None, *, skip_snapshot: bool = False) -> dict:
    month_key = f"{year}-{month:02d}"
    # If this month is locked, return the saved snapshot (don't recompute).
    # skip_snapshot=True bypasses the lock — used by per-recruiter views since
    # snapshots aren't recruiter-tagged.
    if not skip_snapshot and month_key in LOCKED_MONTHS:
        snap = _load_snapshot(month_key)
        if snap is not None:
            return snap

    # Short-circuit for empty input (per-recruiter views with zero matching jobs).
    # df.apply(...) on an empty frame returns a DataFrame, which would break
    # downstream column access.
    if df.empty:
        return _empty_month_payload()

    start, end = month_window(year, month)
    end_ref = end - pd.Timedelta(seconds=1)
    today = pd.Timestamp.now()
    is_current_month = (today >= start) and (today < end)
    ref_now = today if is_current_month else end_ref

    # Roles that were open at some point during this month.
    # On-hold roles do NOT count in SOM (per user). Use SOM_OPEN_THROUGH_OVERRIDES
    # to selectively carry a paused role into a later month if needed.
    def _was_open_during(r):
        if pd.isna(r["open_at"]) or r["open_at"] >= end:
            return False
        # Newly opened in this month: definitely open during this month
        if r["open_at"] >= start:
            return True
        # Manual "still open through" override (caps carry-over for a specific role)
        if pd.notna(r.get("som_open_through")):
            return r["som_open_through"] >= start
        # Effective close = earliest of close_at, offer_acceptance_date
        eff_close = r["close_at"]
        if pd.notna(r["offer_acceptance_date"]):
            eff_close = (
                min(eff_close, r["offer_acceptance_date"])
                if pd.notna(eff_close)
                else r["offer_acceptance_date"]
            )
        if pd.notna(eff_close):
            return eff_close >= start
        # No effective close known — fall back to status: only active still counts
        return r["status"] == STATUS_ACTIVE

    open_during = df[df.apply(_was_open_during, axis=1)]

    # Carry-over: roles open BEFORE this month started (still open as of `start`)
    start_of_month_df = open_during[open_during["open_at"] < start]
    additional_df = open_during[open_during["open_at"] >= start]

    # Currently active subset (status=='active') of open_during.
    # Then drop roles explicitly flagged closed-won via EXCLUDE_FROM_AGING so
    # they disappear from Open / Business View / Aging consistently.
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
        currently_active = currently_active[
            ~currently_active.apply(_excluded_from_aging, axis=1)
        ]
        # Apply per-hash HC reduction (e.g. ORGANIKA X9Y67YXY: 2 → 1 since 1 HC
        # is tracked as For Job Offer via 63VX8VVR). Affects Open/Aging/Business
        # but NOT SoM (which uses start_of_month_df, computed earlier).
        if AGING_HC_REDUCTION and not currently_active.empty:
            currently_active = currently_active.copy()
            currently_active["headcount"] = currently_active.apply(
                lambda r: max(0, _safe_int(r["headcount"]) - AGING_HC_REDUCTION.get(r["hash"], 0)),
                axis=1,
            )
            currently_active = currently_active[currently_active["headcount"] > 0]

    # Closed Won = every role whose offer was accepted in the selected month.
    # Within that pool: "Started" if start_date is on/before today, else "Offer Accepted".
    closed_pool = df[
        df.apply(lambda r: in_window(r["offer_acceptance_date"], start, end), axis=1)
    ]
    today = pd.Timestamp.now()
    started_df = closed_pool[
        closed_pool["start_date"].notna() & (closed_pool["start_date"] <= today)
    ]
    accepted_df = closed_pool[~closed_pool["id"].isin(started_df["id"])]

    def _days(a, b) -> int | None:
        if pd.isna(a) or pd.isna(b):
            return None
        return max(0, (b - a).days)

    closed_won = []
    for _, r in started_df.iterrows():
        closed_won.append({
            "client": r["client_name"], "role": r["position_name"],
            "headcount": _safe_int(r["headcount"]),
            "openedDate": _iso_date(r["open_at"]),
            "offerDate": _iso_date(r["offer_acceptance_date"]),
            "startDate": _iso_date(r["start_date"]),
            "timeToHire": _days(r["open_at"], r["offer_acceptance_date"]),
            "timeToFill": _days(r["open_at"], r["start_date"]),
            "stage": "Started", "type": _organic_kind(r),
        })
    for _, r in accepted_df.iterrows():
        closed_won.append({
            "client": r["client_name"], "role": r["position_name"],
            "headcount": _safe_int(r["headcount"]),
            "openedDate": _iso_date(r["open_at"]),
            "offerDate": _iso_date(r["offer_acceptance_date"]),
            "startDate": _iso_date(r["start_date"]),
            "timeToHire": _days(r["open_at"], r["offer_acceptance_date"]),
            "timeToFill": _days(r["open_at"], r["start_date"]),
            "stage": "Offer Accepted", "type": _organic_kind(r),
        })

    # Virtual closed-won entries: roles that don't have their own Manatal record
    # (used to express partial-HC splits, e.g. ORGANIKA HC=2 → 1 closed + 1 active).
    virtual_cw_hc_this_month = 0
    for h, v in CLOSED_WON_VIRTUAL_HASHES.items():
        if v.get("month") != month_key:
            continue
        if not v.get("client") or not v.get("role"):
            continue
        virtual_cw_hc_this_month += int(v.get("hc", 0))
        closed_won.append({
            "client": v["client"],
            "role": v["role"],
            "headcount": int(v.get("hc", 1)),
            "openedDate": v.get("openedDate", ""),
            "offerDate": v.get("offerDate", ""),
            "startDate": "",
            "timeToHire": None,
            "timeToFill": None,
            "stage": "Offer Accepted",
            "type": v.get("type", "Ramp"),
        })

    # Pipeline KPIs
    # "For Job Offer" combines:
    #   1) Manual IN_OFFER_HASHES (scoped by month) — authoritative, never filtered.
    #   2) Auto-detected matches in the "Job Offer" pipeline stage from Manatal,
    #      counted in the CURRENT month only and filtered through EXCLUDE_IN_OFFER.
    today_now = pd.Timestamp.now()
    in_offer_for_this_month = {
        h: v["hc"] for h, v in IN_OFFER_HASHES.items() if v.get("month") == month_key
    }

    def _is_auto_excluded(h: str) -> bool:
        row = df[df["hash"] == h]
        if row.empty:
            return False
        r = row.iloc[0]
        key = (
            str(r["client_name"]).strip().upper(),
            str(r["position_name"]).strip().upper(),
        )
        return key in EXCLUDE_IN_OFFER

    if is_current_month and auto_in_offer:
        for h, hc in auto_in_offer.items():
            if _is_auto_excluded(h):
                continue
            in_offer_for_this_month[h] = max(in_offer_for_this_month.get(h, 0), int(hc))

    # Once a role's offer has been accepted (offer_acceptance_date is set),
    # it belongs in Closed Won — drop it from For Job Offer even if pinned
    # in IN_OFFER_HASHES. Lets manual entries auto-revoke when Manatal syncs.
    if "offer_acceptance_date" in df.columns:
        accepted_hashes = set(df.loc[df["offer_acceptance_date"].notna(), "hash"])
        in_offer_for_this_month = {
            h: hc for h, hc in in_offer_for_this_month.items() if h not in accepted_hashes
        }

    in_offer_hc = sum(in_offer_for_this_month.values())

    # Build details for the For Job Offer table (same shape as closedWon items)
    in_offer_roles = []
    for h, hc in in_offer_for_this_month.items():
        row = df[df["hash"] == h]
        if row.empty:
            # Fallback: hash excluded from df (e.g. EXCLUDE_HASHES). Use metadata
            # baked into IN_OFFER_HASHES so the detail row still renders.
            meta = IN_OFFER_HASHES.get(h, {})
            if not meta.get("client") or not meta.get("role"):
                continue
            in_offer_roles.append({
                "client": meta["client"],
                "role": meta["role"],
                "headcount": int(hc),
                "startDate": "",
                "stage": "Offer Extended",
                "type": meta.get("type", "Ramp"),
            })
            continue
        r = row.iloc[0]
        in_offer_roles.append({
            "client": r["client_name"],
            "role": r["position_name"],
            "headcount": int(hc),
            "startDate": _iso_date(r["start_date"]),
            "stage": "Offer Extended",
            "type": _organic_kind(r),
        })
    # ----- Ongoing Contract (post-offer, pre-acceptance) -----
    # Manually curated dict, scoped by month. Same metadata-fallback pattern
    # as IN_OFFER_HASHES — supports hashes that are EXCLUDE_HASHES-excluded.
    ongoing_contract_for_this_month = {
        h: v["hc"] for h, v in ONGOING_CONTRACT_HASHES.items() if v.get("month") == month_key
    }
    # Same auto-drop logic: if Manatal records an offer acceptance, the role
    # is no longer "ongoing" — it's offered/accepted.
    if "offer_acceptance_date" in df.columns:
        accepted_h = set(df.loc[df["offer_acceptance_date"].notna(), "hash"])
        ongoing_contract_for_this_month = {
            h: hc for h, hc in ongoing_contract_for_this_month.items() if h not in accepted_h
        }
    ongoing_contract_hc = sum(ongoing_contract_for_this_month.values())

    ongoing_contract_roles = []
    for h, hc in ongoing_contract_for_this_month.items():
        row = df[df["hash"] == h]
        if row.empty:
            meta = ONGOING_CONTRACT_HASHES.get(h, {})
            if not meta.get("client") or not meta.get("role"):
                continue
            ongoing_contract_roles.append({
                "client": meta["client"],
                "role": meta["role"],
                "headcount": int(hc),
                "startDate": "",
                "stage": "Ongoing Contract",
                "type": meta.get("type", "Ramp"),
            })
            continue
        r = row.iloc[0]
        ongoing_contract_roles.append({
            "client": r["client_name"],
            "role": r["position_name"],
            "headcount": int(hc),
            "startDate": _iso_date(r["start_date"]),
            "stage": "Ongoing Contract",
            "type": _organic_kind(r),
        })

    paused_in_month = open_during[
        (open_during["status"] == STATUS_ON_HOLD)
        & open_during["close_at"].between(start, end - pd.Timedelta(seconds=1))
    ]
    # "Open / Active" is a CURRENT-state metric, not a historical month metric.
    # For past months, show 0 — those still-open roles roll forward and are
    # already counted in the current month's snapshot.
    # currently_active already has AGING_HC_REDUCTION applied, so the sum
    # naturally excludes HC tracked as For Job Offer.
    if is_current_month:
        open_count = int(currently_active["headcount"].fillna(1).sum() or 0)
    else:
        open_count = 0
    pipeline = {
        "open": open_count,
        "forJobOffer": int(in_offer_hc),
        "ongoingContract": int(ongoing_contract_hc),
        "offerAccepted": int(accepted_df["headcount"].fillna(1).sum() or 0) + int(virtual_cw_hc_this_month),
        "started": int(started_df["headcount"].fillna(1).sum() or 0),
        "paused": int(paused_in_month["headcount"].fillna(1).sum() or 0),
    }

    # Business view & Role Aging are CURRENT-state metrics, not historical.
    # `currently_active` is already filtered by EXCLUDE_FROM_AGING above.
    if is_current_month:
        aging_pool = currently_active
        new_logo = aging_pool[aging_pool["role_type"] == "New Logo"]
        ramp = aging_pool[
            (aging_pool["role_type"] == "Organic")
            & (aging_pool["organic_subtype"] == "Ramp")
        ]
        backfill = aging_pool[
            (aging_pool["role_type"] == "Organic")
            & (aging_pool["organic_subtype"] == "Backfill")
        ]
        business = {
            "newLogoCount": int(new_logo["headcount"].fillna(1).sum() or 0),
            "rampCount": int(ramp["headcount"].fillna(1).sum() or 0),
            "backfillCount": int(backfill["headcount"].fillna(1).sum() or 0),
            "newLogoJobs": [_job_brief(r, ref_now) for _, r in new_logo.iterrows()],
            "rampJobs": [_job_brief(r, ref_now) for _, r in ramp.iterrows()],
            "backfillJobs": [_job_brief(r, ref_now) for _, r in backfill.iterrows()],
        }
        counts = _aging_bucket_counts(aging_pool, ref_now)
        aging_jobs = []
        if not aging_pool.empty:
            sorted_active = aging_pool.assign(
                _days=aging_pool.apply(lambda r: _age_in_days(r, ref_now), axis=1)
            ).sort_values("_days", ascending=False)
            for _, r in sorted_active.iterrows():
                aging_jobs.append(_job_brief(r, ref_now))
        aging = {
            "avgNewLogo": _avg_days(new_logo, ref_now),
            "avgRamp": _avg_days(ramp, ref_now),
            "avgBackfill": _avg_days(backfill, ref_now),
            **counts,
            "jobs": aging_jobs,
        }
    else:
        business = {
            "newLogoCount": 0, "rampCount": 0, "backfillCount": 0,
            "newLogoJobs": [], "rampJobs": [], "backfillJobs": [],
        }
        aging = {
            "avgNewLogo": 0, "avgRamp": 0, "avgBackfill": 0,
            "fresh": 0, "normal": 0, "aging": 0, "critical": 0,
            "jobs": [],
        }

    # Paused roles paused IN this month (close_at = pause date for on_hold roles).
    # Priority for pause date: event_date_override (manual) > close_at > updated_at.
    paused_now = df[df["status"] == STATUS_ON_HOLD].copy()
    paused_now["_pause_date"] = (
        paused_now["event_date_override"]
        .fillna(paused_now["close_at"])
        .fillna(paused_now["updated_at"])
    )
    paused_now = paused_now[
        paused_now["_pause_date"].between(start, end - pd.Timedelta(seconds=1))
    ]
    paused_roles = []
    for _, r in paused_now.iterrows():
        paused_roles.append({
            "client": r["client_name"], "role": r["position_name"],
            "headcount": _safe_int(r["headcount"]),
            "pausedDate": _iso_date(r["_pause_date"]),
            "reason": extract_pause_reason(r["recruiter_remarks"]),
            "type": _organic_kind(r),
        })

    # Closed Lost — roles closed-lost in this month.
    # Priority: event_date_override > close_at > updated_at.
    lost_now = df[df["status"] == STATUS_LOST].copy()
    lost_now["_lost_date"] = (
        lost_now["event_date_override"]
        .fillna(lost_now["close_at"])
        .fillna(lost_now["updated_at"])
    )
    lost_now = lost_now[lost_now["_lost_date"].between(start, end - pd.Timedelta(seconds=1))]
    closed_lost_roles = []
    for _, r in lost_now.iterrows():
        closed_lost_roles.append({
            "client": r["client_name"], "role": r["position_name"],
            "headcount": _safe_int(r["headcount"]),
            "lostDate": _iso_date(r["_lost_date"]),
            "reason": extract_pause_reason(r["recruiter_remarks"]),
            "type": _organic_kind(r),
        })

    # Count HEADCOUNT, not roles — to align with Closed Won (also HC-based).
    start_of_month_hc = int(start_of_month_df["headcount"].fillna(1).sum() or 0)
    additional_hc = int(additional_df["headcount"].fillna(1).sum() or 0)
    monthly_target = math.ceil(start_of_month_hc * 0.70)

    # Time metrics, averaged over roles whose offer was accepted in this month.
    # Time-to-Hire  = days from open_at to offer_acceptance_date.
    # Time-to-Fill  = days from open_at to start_date (only roles that have started).
    def _avg_days_between(d, col_a: str, col_b: str) -> int:
        if d.empty:
            return 0
        sub = d[d[col_a].notna() & d[col_b].notna()]
        if sub.empty:
            return 0
        return int((sub[col_b] - sub[col_a]).dt.days.mean())

    time_to_hire = _avg_days_between(closed_pool, "open_at", "offer_acceptance_date")
    time_to_fill = _avg_days_between(closed_pool, "open_at", "start_date")

    # Detail rows for the SOM "View carry-over roles" panel.
    som_carry_over = []
    if not start_of_month_df.empty:
        sorted_som = start_of_month_df.sort_values("open_at")
        for _, r in sorted_som.iterrows():
            som_carry_over.append({
                "client": r["client_name"],
                "role": r["position_name"],
                "headcount": _safe_int(r["headcount"]),
                "opened": _iso_date(r["open_at"]),
                "days": _age_in_days(r, ref_now),
                "type": _organic_kind(r),
                "status": r["status"],
            })

    return {
        "totalOpen": open_count,
        "startOfMonth": start_of_month_hc,
        "startOfMonthRoles": len(start_of_month_df),
        "additionalInMonth": additional_hc,
        "additionalInMonthRoles": len(additional_df),
        "monthlyTarget": monthly_target,
        "pipeline": pipeline,
        "pausedRoles": paused_roles,
        "closedLostRoles": closed_lost_roles,
        "closedWon": closed_won,
        "inOfferRoles": in_offer_roles,
        "ongoingContractRoles": ongoing_contract_roles,
        "ongoingContract": int(ongoing_contract_hc),
        "somCarryOver": som_carry_over,
        "business": business,
        "aging": aging,
        "avgTimeToHire": time_to_hire,
        "avgTimeToFill": time_to_fill,
        "activeRequisitions": open_count,
        "activeRequisitionsRoles": int(len(currently_active)) if not currently_active.empty else 0,
    }


def _build_monthly_trend(df: pd.DataFrame, months: list[dict], all_months: dict | None = None) -> list[dict]:
    """Monthly trend bars (Opened HC vs Filled HC) + fill-rate % + per-type aging.
    For locked months, derives values from the snapshot so the chart is stable."""
    rows = []
    for m in months:
        key = m["value"]
        y, mo = int(key[:4]), int(key[5:7])
        md = all_months.get(key) if all_months else None
        if md is not None:
            opened = int(md.get("additionalInMonth", 0))
            filled = int(sum(r.get("headcount", 1) for r in md.get("closedWon", [])))
        elif df.empty:
            opened = 0
            filled = 0
        else:
            start, end = month_window(y, mo)
            mask_open = df["open_at"].between(start, end - pd.Timedelta(seconds=1))
            opened = int(df.loc[mask_open, "headcount"].fillna(1).sum() or 0)
            mask_won = (df["status"] == STATUS_WON) & df["close_at"].between(
                start, end - pd.Timedelta(seconds=1)
            )
            filled = int(df.loc[mask_won, "headcount"].fillna(1).sum() or 0)

        # Fill rate = (Closed Won + In Offer) / SOM * 100
        som_hc = int(md.get("startOfMonth", 0)) if md else 0
        cw_hc = int(sum(r.get("headcount", 1) for r in (md.get("closedWon", []) if md else [])))
        io_hc = int(sum(r.get("headcount", 1) for r in (md.get("inOfferRoles", []) if md else [])))
        oc_hc = int(sum(r.get("headcount", 1) for r in (md.get("ongoingContractRoles", []) if md else [])))
        fill_rate = round((cw_hc + io_hc + oc_hc) / som_hc * 100) if som_hc > 0 else 0

        # Per-type aging averages (New Logo vs Organic = avg of Ramp + Backfill)
        aging = (md.get("aging") if md else {}) or {}
        avg_nl = int(aging.get("avgNewLogo", 0) or 0)
        avg_ramp = int(aging.get("avgRamp", 0) or 0)
        avg_backfill = int(aging.get("avgBackfill", 0) or 0)
        # "Organic" = simple average of Ramp + Backfill (ignoring zeros so a
        # month with only one active organic type isn't halved)
        organic_vals = [v for v in (avg_ramp, avg_backfill) if v > 0]
        avg_organic = int(sum(organic_vals) / len(organic_vals)) if organic_vals else 0

        rows.append({
            "month": key,
            "label": dt.date(y, mo, 1).strftime("%b"),
            "opened": opened,
            "filled": filled,
            "fillRate": fill_rate,
            "avgAgingNewLogo": avg_nl,
            "avgAgingRamp": avg_ramp,
            "avgAgingBackfill": avg_backfill,
            "avgAgingOrganic": avg_organic,
        })
    return rows


def _job_offer_matches_to_hc(df: pd.DataFrame, matches: list[dict]) -> dict[str, int]:
    """Aggregate active 'Job Offer' pipeline matches into {hash: candidate_count}."""
    if not matches:
        return {}
    id_to_hash = dict(zip(df["id"], df["hash"]))
    out: dict[str, int] = {}
    for m in matches:
        job_ref = m.get("job")
        if isinstance(job_ref, dict):
            job_id = job_ref.get("id")
        else:
            job_id = job_ref
        h = id_to_hash.get(job_id)
        if not h:
            continue
        out[h] = out.get(h, 0) + 1
    return out


def _candidate_pipeline_by_recruiter(
    df: pd.DataFrame, matches: list[dict] | None
) -> dict[str, dict]:
    """Bucket active candidate matches by recruiter and pipeline stage.
    Returns {recruiter_display: {endorsed, clientInterview, pendingReview, ...}}.

    Stage classification by substring match against Manatal's `job_pipeline_stage.name`:
      - "endors"           → endorsed (sent to client for review)
      - "client interview" → clientInterview (interview scheduled with client)
      - "pending"          → pendingReview (explicit pending bucket)
    """
    out: dict[str, dict] = {disp: {
        "endorsed": 0, "clientInterview": 0, "pendingReview": 0,
        "details": [],
    } for disp, _ in RECRUITERS}
    if not matches or df.empty:
        return out

    # Limit to jobs that are still OPEN — status == active AND not flagged as
    # closed-won via EXCLUDE_FROM_AGING. Candidates against closed/won/lost
    # jobs aren't really "in pipeline" anymore.
    def _is_open_role(r) -> bool:
        if r.get("status") != STATUS_ACTIVE:
            return False
        cl = str(r.get("client_name") or "").upper()
        pos = str(r.get("position_name") or "").upper()
        kind = _organic_kind(r) if r.get("role_type") else None
        for ec, ep, ek in EXCLUDE_FROM_AGING:
            if ec in cl and ep in pos and (ek is None or ek == kind):
                return False
        return True

    open_ids = set(int(jid) for jid in df.loc[df.apply(_is_open_role, axis=1), "id"])

    id_to_hash = dict(zip(df["id"], df["hash"]))
    id_to_client = dict(zip(df["id"], df["client_name"]))
    id_to_role = dict(zip(df["id"], df["position_name"]))
    id_to_owner = dict(zip(df["id"], df["owner_name"].fillna("").str.lower()))
    hash_to_recruiter = dict(RECRUITER_OVERRIDES)

    def _recruiter_for_job(job_id) -> str | None:
        h = id_to_hash.get(job_id)
        if h and h in hash_to_recruiter:
            return hash_to_recruiter[h]
        owner = id_to_owner.get(job_id, "")
        for disp, needles in RECRUITERS:
            if any(n.lower() in owner for n in needles):
                return disp
        return None

    for m in matches:
        job_ref = m.get("job")
        job_id = job_ref.get("id") if isinstance(job_ref, dict) else job_ref
        # Skip candidates whose job is no longer open/active
        if job_id not in open_ids:
            continue
        recruiter = _recruiter_for_job(job_id)
        if not recruiter or recruiter not in out:
            continue
        stage_name = ((m.get("job_pipeline_stage") or {}).get("name") or "").strip()
        stage_lower = stage_name.lower()
        bucket: str | None = None
        if "client interview" in stage_lower:
            bucket = "clientInterview"
        elif "endors" in stage_lower:
            bucket = "endorsed"
        elif "pending" in stage_lower and "client" in stage_lower:
            bucket = "pendingReview"
        if not bucket:
            continue
        out[recruiter][bucket] += 1
        cand = m.get("candidate") or {}
        cand_name = cand.get("full_name") if isinstance(cand, dict) else None
        out[recruiter]["details"].append({
            "candidate": cand_name or "Candidate",
            "client": id_to_client.get(job_id, ""),
            "role": id_to_role.get(job_id, ""),
            "stage": stage_name,
            "bucket": bucket,
        })
    return out


def _open_jobs_candidate_funnel(df: pd.DataFrame, matches: list[dict] | None) -> list[dict]:
    """Per-open-role candidate funnel across Initial Interview, Client Endorsement, Client Interview.

    Manual override — the raw Manatal matches API returns candidate as a bare integer ID,
    so we can't resolve full names inline. If `data/candidate_funnel_override.json` exists,
    return its `roles` array wrapped into the same shape used by the frontend.
    """
    override_path = Path(__file__).parent.parent / "data" / "candidate_funnel_override.json"
    if override_path.exists():
        try:
            # utf-8-sig handles BOM-prefixed files (PowerShell 5.1 Set-Content writes BOM)
            with override_path.open("r", encoding="utf-8-sig") as f:
                override = json.load(f)

            def _norm(item, stage_name):
                """Accept either a string (name only) or a dict {name, movedAt}."""
                if isinstance(item, dict):
                    return {
                        "name": item.get("name", "Candidate"),
                        "movedAt": item.get("movedAt", ""),
                        "stage": stage_name,
                    }
                return {"name": str(item), "movedAt": "", "stage": stage_name}

            out = []
            for r in (override.get("roles") or []):
                out.append({
                    "hash": r.get("hash", ""),
                    "client": r.get("client", ""),
                    "role": r.get("role", ""),
                    "hc": int(r.get("hc") or 1),
                    "opened": r.get("opened", ""),
                    "days": int(r.get("days") or 0),
                    "type": r.get("type", ""),
                    "initialInterview":  [_norm(x, "Initial Interview")  for x in (r.get("initialInterview")  or [])],
                    "clientEndorsement": [_norm(x, "Client Endorsement") for x in (r.get("clientEndorsement") or [])],
                    "clientInterview":   [_norm(x, "Client Interview")   for x in (r.get("clientInterview")   or [])],
                    "jobOffer":          [_norm(x, "Job Offer")          for x in (r.get("jobOffer")          or [])],
                    "ongoingContract":   [_norm(x, "On-going Contract")  for x in (r.get("ongoingContract")   or [])],
                    "offerAccepted":     [_norm(x, "Offer Accepted")     for x in (r.get("offerAccepted")     or [])],
                })
            out.sort(key=lambda x: (-x["days"], x["client"]))
            return out
        except Exception:
            pass  # fall through to live API path

    def _is_open_role(r) -> bool:
        if r.get("status") != STATUS_ACTIVE:
            return False
        cl = str(r.get("client_name") or "").upper()
        pos = str(r.get("position_name") or "").upper()
        kind = _organic_kind(r) if r.get("role_type") else None
        for ec, ep, ek in EXCLUDE_FROM_AGING:
            if ec in cl and ep in pos and (ek is None or ek == kind):
                return False
        return True

    if df.empty:
        return []

    open_df = df[df.apply(_is_open_role, axis=1)].copy()
    if open_df.empty:
        return []

    ref_now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    by_id: dict[int, dict] = {}
    for _, r in open_df.iterrows():
        jid = int(r["id"])
        opened = r.get("open_at")
        days = 0
        if pd.notna(opened):
            days = max(0, int((ref_now - pd.Timestamp(opened).tz_localize(None) if pd.Timestamp(opened).tzinfo else ref_now - pd.Timestamp(opened)).days))
        by_id[jid] = {
            "hash": r.get("hash"),
            "client": r.get("client_name") or "",
            "role": r.get("position_name") or "",
            "hc": int(r.get("headcount") or 1),
            "opened": pd.Timestamp(opened).strftime("%Y-%m-%d") if pd.notna(opened) else "",
            "days": days,
            "type": r.get("role_type") or "",
            "initialInterview": [],
            "clientEndorsement": [],
            "clientInterview": [],
        }

    for m in (matches or []):
        job_ref = m.get("job")
        jid = job_ref.get("id") if isinstance(job_ref, dict) else job_ref
        if jid not in by_id:
            continue
        stage_name = ((m.get("job_pipeline_stage") or {}).get("name") or "").strip()
        stage_lower = stage_name.lower()
        cand = m.get("candidate") or {}
        cand_name = (cand.get("full_name") if isinstance(cand, dict) else None) or "Candidate"
        row = {"name": cand_name, "stage": stage_name}
        if "client interview" in stage_lower:
            by_id[jid]["clientInterview"].append(row)
        elif "endors" in stage_lower:
            by_id[jid]["clientEndorsement"].append(row)
        elif "initial" in stage_lower or "screening" in stage_lower or "screen" in stage_lower:
            by_id[jid]["initialInterview"].append(row)

    result = list(by_id.values())
    result.sort(key=lambda x: (-x["days"], x["client"]))
    return result


def build_payload(df: pd.DataFrame, job_offer_matches: list[dict] | None = None, active_matches: list[dict] | None = None) -> tuple[dict, list[dict], str]:
    """Returns (data_dict, available_months, default_selected_month)."""
    months = available_months()
    today = dt.date.today()
    default_sel = f"{today.year}-{today.month:02d}"
    if default_sel not in {m["value"] for m in months}:
        default_sel = months[-1]["value"]

    auto_in_offer = _job_offer_matches_to_hc(df, job_offer_matches or [])
    candidate_pipeline = _candidate_pipeline_by_recruiter(df, active_matches)
    open_jobs_funnel = _open_jobs_candidate_funnel(df, active_matches)

    all_months = {}
    for m in months:
        y, mo = int(m["value"][:4]), int(m["value"][5:7])
        all_months[m["value"]] = _build_month(df, y, mo, auto_in_offer=auto_in_offer)

    sel_y, sel_m = int(default_sel[:4]), int(default_sel[5:7])
    sel_data = all_months[default_sel]
    monthly_trend = _build_monthly_trend(df, months, all_months)

    # ----- Recruiter View: per-recruiter slice of every month -----
    # For each recruiter, filter df to roles whose owner_name matches any of the
    # configured substrings, PLUS hashes manually pinned to them via
    # RECRUITER_OVERRIDES. Re-run _build_month over that subset.
    by_recruiter: dict[str, dict] = {}
    owner_lower = df["owner_name"].fillna("").str.lower() if "owner_name" in df.columns else None
    # Inverted index of manual recruiter assignments: display label -> set(hash)
    overrides_by_display: dict[str, set[str]] = {}
    for h, disp in RECRUITER_OVERRIDES.items():
        overrides_by_display.setdefault(disp, set()).add(h)
    # Hashes that are manually assigned to ANYONE — exclude them from name-based
    # matching so a role can't appear under two recruiters at once.
    pinned_hashes = set(RECRUITER_OVERRIDES.keys())
    for display, needles in RECRUITERS:
        if owner_lower is None:
            sub_df = df.iloc[0:0]
        else:
            mask = pd.Series(False, index=df.index)
            for n in needles:
                mask = mask | owner_lower.str.contains(n.lower(), na=False)
            # Drop any role that's manually pinned (will be re-added below for its owner)
            if pinned_hashes:
                mask = mask & ~df["hash"].isin(pinned_hashes)
            # Add this recruiter's pinned hashes
            pinned_for_this = overrides_by_display.get(display, set())
            if pinned_for_this:
                mask = mask | df["hash"].isin(pinned_for_this)
            sub_df = df[mask]
        sub_auto = {
            h: hc for h, hc in (auto_in_offer or {}).items() if h in set(sub_df["hash"])
        }
        per_recruiter_months: dict[str, dict] = {}
        for m in months:
            y, mo = int(m["value"][:4]), int(m["value"][5:7])
            per_recruiter_months[m["value"]] = _build_month(
                sub_df, y, mo, auto_in_offer=sub_auto, skip_snapshot=True
            )
        cand = candidate_pipeline.get(display, {"endorsed": 0, "clientInterview": 0, "pendingReview": 0, "details": []})
        by_recruiter[display] = {
            "months": per_recruiter_months,
            "monthly": _build_monthly_trend(sub_df, months),
            "roleCount": int(len(sub_df)),
            "hcTotal": int(sub_df["headcount"].fillna(1).sum() or 0) if not sub_df.empty else 0,
            "candidates": cand,
        }

    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "month": default_sel,
        "totalOpen": sel_data["totalOpen"],
        "startOfMonth": sel_data["startOfMonth"],
        "startOfMonthRoles": sel_data["startOfMonthRoles"],
        "additionalInMonth": sel_data["additionalInMonth"],
        "additionalInMonthRoles": sel_data["additionalInMonthRoles"],
        "monthlyTarget": sel_data["monthlyTarget"],
        "pipeline": sel_data["pipeline"],
        "pausedRoles": sel_data["pausedRoles"],
        "closedLostRoles": sel_data["closedLostRoles"],
        "closedWon": sel_data["closedWon"],
        "inOfferRoles": sel_data.get("inOfferRoles", []),
        "ongoingContractRoles": sel_data.get("ongoingContractRoles", []),
        "somCarryOver": sel_data.get("somCarryOver", []),
        "business": sel_data["business"],
        "aging": sel_data["aging"],
        "monthly": monthly_trend,
        "allMonths": all_months,
        "byRecruiter": by_recruiter,
        "recruiters": [r[0] for r in RECRUITERS],
        "openJobsFunnel": open_jobs_funnel,
        "nurtureList": _load_nurture_list(),
        "recruitmentMetrics": _load_recruitment_metrics(),
        "recruiterMetrics": _load_recruiter_metrics(),
    }
    return payload, months, default_sel


def _load_recruiter_metrics() -> dict:
    """Per-recruiter recruitment metrics from data/recruiter_metrics.json.
    Populated by /update-recruiter-metrics. utf-8-sig for BOM tolerance."""
    p = Path(__file__).parent.parent / "data" / "recruiter_metrics.json"
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_recruitment_metrics() -> dict:
    """Load the Recruitment Metrics data from data/recruitment_metrics.json.
    Populated by /update-recruitment-metrics skill (pulls Manatal + snapshots).

    Uses utf-8-sig so a UTF-8 BOM (which PowerShell 5.1 Set-Content adds by default)
    doesn't silently break json.load and empty the tab."""
    p = Path(__file__).parent.parent / "data" / "recruitment_metrics.json"
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}


def _load_nurture_list() -> dict:
    """Load the Nurture List Funnel data from data/nurture_list.json.
    Refreshed daily via /update-nurture-list skill (reads from Google Sheet).
    utf-8-sig handles BOM-prefixed files transparently."""
    p = Path(__file__).parent.parent / "data" / "nurture_list.json"
    if not p.exists():
        return {}
    try:
        with p.open("r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception:
        return {}
