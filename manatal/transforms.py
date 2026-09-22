import re
import datetime as dt
from html import unescape

import pandas as pd

from .constants import (
    STATUS_ACTIVE,
    STATUS_WON,
    STATUS_LOST,
    STATUS_ON_HOLD,
    STATUS_OVERRIDES,
    EVENT_DATE_OVERRIDES,
    OFFER_ACCEPTANCE_OVERRIDES,
    OPEN_AT_OVERRIDES,
    SOM_OPEN_THROUGH_OVERRIDES,
    TYPE_OVERRIDES,
    NAME_BASED_TYPE_OVERRIDES,
    HEADCOUNT_OVERRIDES,
    AGING_BUCKETS,
    ORGANIC_VALUES,
)

_HTML_RE = re.compile(r"<[^>]+>")
_PAUSE_PATTERNS = [
    (r"client\s+initiated", "Client initiated"),
    (r"on\s+hold", "On hold"),
    (r"pause(d)?\s+by\s+client", "Paused by client"),
    (r"budget", "Budget"),
    (r"hir(ed|ing)\s+from\s+(another|other)", "Hired elsewhere"),
    (r"req(uirement)?\s+chang", "Requirement change"),
    (r"position\s+cancel", "Position cancelled"),
    (r"replac(ed|ement)", "Replacement found"),
    (r"intern(al)?\s+hir", "Internal hire"),
]


def strip_html(s: str | None) -> str:
    if not s:
        return ""
    return unescape(_HTML_RE.sub(" ", s)).replace("\xa0", " ").strip()


def extract_pause_reason(remark_html: str | None) -> str:
    text = strip_html(remark_html).lower()
    if not text:
        return "Unspecified"
    for pat, label in _PAUSE_PATTERNS:
        if re.search(pat, text):
            return label
    return "Other"


def parse_dt(value) -> pd.Timestamp | None:
    if not value:
        return None
    try:
        return pd.to_datetime(value, utc=True).tz_convert(None)
    except Exception:
        return None


def _user_display_name(u: dict) -> str:
    full = (u.get("full_name") or "").strip()
    if full:
        return full
    fn = (u.get("first_name") or "").strip()
    ln = (u.get("last_name") or "").strip()
    name = f"{fn} {ln}".strip()
    return name or (u.get("email") or "").strip()


def jobs_to_frame(jobs: list[dict], orgs: list[dict], users: list[dict] | None = None) -> pd.DataFrame:
    org_by_id = {o["id"]: o.get("name") or "" for o in orgs}
    user_by_id = {u["id"]: _user_display_name(u) for u in (users or []) if u.get("id") is not None}
    rows = []
    for j in jobs:
        cf = j.get("custom_fields") or {}
        hash_code = j.get("hash") or ""
        raw_status = j.get("status") or ""
        # Apply manual overrides (constants.STATUS_OVERRIDES) keyed by hash
        effective_status = STATUS_OVERRIDES.get(hash_code, raw_status)
        # Capture event-date override (used ONLY for paused/closed-lost classification,
        # not for SOM / open-during filtering).
        event_date_override = EVENT_DATE_OVERRIDES.get(hash_code)
        rows.append(
            {
                "id": j["id"],
                "hash": hash_code,
                "position_name": j.get("position_name") or "",
                "organization_id": j.get("organization"),
                "organization_name": org_by_id.get(j.get("organization"), ""),
                "client_name_field": (cf.get("clientname") or "").strip() or None,
                "headcount": HEADCOUNT_OVERRIDES.get(hash_code, j.get("headcount") or 1),
                "status": effective_status,
                "raw_status": raw_status,
                "event_date_override": event_date_override,
                "som_open_through": SOM_OPEN_THROUGH_OVERRIDES.get(hash_code),
                "justification": (cf.get("justification") or "").upper().strip(),
                "start_date": parse_dt(cf.get("startdate")),
                "offer_acceptance_date": parse_dt(
                    OFFER_ACCEPTANCE_OVERRIDES.get(hash_code, cf.get("offeracceptancedate"))
                ),
                "open_at": parse_dt(
                    OPEN_AT_OVERRIDES.get(hash_code, j.get("open_at") or j.get("created_at"))
                ),
                "close_at": parse_dt(
                    EVENT_DATE_OVERRIDES.get(hash_code, j.get("close_at"))
                ),
                "expected_close_at": parse_dt(j.get("expected_close_at")),
                "updated_at": parse_dt(j.get("updated_at")),
                "owner": j.get("owner"),
                "owner_name": user_by_id.get(j.get("owner"), ""),
                "creator": j.get("creator"),
                "recruiter_remarks": cf.get("recruiterremarks") or "",
                "role_classification": ", ".join(cf.get("roleclassification") or []),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df["event_date_override"] = df["event_date_override"].apply(parse_dt)
    df["som_open_through"] = df["som_open_through"].apply(parse_dt)

    # Display client name: use Manatal organization (Clients module) name;
    # only fall back to the clientname custom field if org name is missing.
    df["client_name"] = (
        df["organization_name"]
        .replace("", pd.NA)
        .fillna(df["client_name_field"])
        .fillna("Unknown")
    )

    # Role type derivation: New Logo = first role for that org by open_at
    first_open = df.sort_values("open_at").groupby("organization_id")["id"].first()
    new_logo_ids = set(first_open.values)
    df["role_type"] = df.apply(
        lambda r: "New Logo" if r["id"] in new_logo_ids else "Organic", axis=1
    )

    # Organic subtype
    def _subtype(row):
        if row["role_type"] != "Organic":
            return None
        j = (row["justification"] or "").upper()
        if "BACKFILL" in j:
            return "Backfill"
        if "RAMP" in j:
            return "Ramp"
        return "Ramp"  # default for organic without explicit tag

    df["organic_subtype"] = df.apply(_subtype, axis=1)

    # Apply manual type overrides (constants.TYPE_OVERRIDES) keyed by hash
    def _apply_type_override(row):
        ov = TYPE_OVERRIDES.get(row["hash"])
        if not ov:
            return row
        if ov == "New Logo":
            row["role_type"] = "New Logo"
            row["organic_subtype"] = None
        elif ov == "Ramp":
            row["role_type"] = "Organic"
            row["organic_subtype"] = "Ramp"
        elif ov == "Backfill":
            row["role_type"] = "Organic"
            row["organic_subtype"] = "Backfill"
        return row

    df = df.apply(_apply_type_override, axis=1)

    # Apply name-based type overrides (constants.NAME_BASED_TYPE_OVERRIDES),
    # keyed by (client substring, position substring). Hash-based overrides above
    # take precedence — only rows still without a forced type are matched here.
    def _apply_name_type_override(row):
        if row["hash"] in TYPE_OVERRIDES:
            return row
        cl = str(row["client_name"]).upper()
        pos = str(row["position_name"]).upper()
        for (ec, ep), ov in NAME_BASED_TYPE_OVERRIDES.items():
            if ec in cl and ep in pos:
                if ov == "New Logo":
                    row["role_type"] = "New Logo"
                    row["organic_subtype"] = None
                elif ov == "Ramp":
                    row["role_type"] = "Organic"
                    row["organic_subtype"] = "Ramp"
                elif ov == "Backfill":
                    row["role_type"] = "Organic"
                    row["organic_subtype"] = "Backfill"
                break
        return row

    df = df.apply(_apply_name_type_override, axis=1)

    # Pause reason
    df["pause_reason"] = df["recruiter_remarks"].apply(extract_pause_reason)
    df["remarks_text"] = df["recruiter_remarks"].apply(strip_html)
    return df


def is_open_at(row, ts: pd.Timestamp) -> bool:
    """Was this role open (not yet closed) at moment ts?"""
    if pd.isna(row["open_at"]) or row["open_at"] > ts:
        return False
    if row["status"] == STATUS_ACTIVE:
        return True
    close = row["close_at"] if pd.notna(row["close_at"]) else row["updated_at"]
    if pd.isna(close):
        return True
    return close >= ts


def days_open_as_of(row, ts: pd.Timestamp) -> int | None:
    if pd.isna(row["open_at"]):
        return None
    if not is_open_at(row, ts):
        # for closed roles, days open until close
        end = row["close_at"] if pd.notna(row["close_at"]) else row["updated_at"]
        if pd.isna(end):
            return None
        return max(0, (end - row["open_at"]).days)
    return max(0, (ts - row["open_at"]).days)


def aging_bucket(days: int | None) -> str:
    if days is None:
        return "Unknown"
    for label, lo, hi in AGING_BUCKETS:
        if lo <= days <= hi:
            return label
    return "Critical"


def month_window(year: int, month: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(year=year, month=month, day=1)
    if month == 12:
        end = pd.Timestamp(year=year + 1, month=1, day=1)
    else:
        end = pd.Timestamp(year=year, month=month + 1, day=1)
    return start, end


def in_window(value, start, end) -> bool:
    return pd.notna(value) and start <= value < end


def funnel_metrics(df: pd.DataFrame, year: int, month: int) -> dict:
    start, end = month_window(year, month)

    carry_over = df[df.apply(lambda r: is_open_at(r, start) and r["open_at"] < start, axis=1)]
    newly_opened = df[df.apply(lambda r: in_window(r["open_at"], start, end), axis=1)]
    total_open = pd.concat([carry_over, newly_opened]).drop_duplicates("id")

    in_offer = df[
        df.apply(
            lambda r: pd.notna(r["offer_acceptance_date"])
            and is_open_at(r, end - pd.Timedelta(seconds=1))
            and r["offer_acceptance_date"] < end,
            axis=1,
        )
    ]
    offer_accepted = df[
        df.apply(lambda r: in_window(r["offer_acceptance_date"], start, end), axis=1)
    ]
    started = df[df.apply(lambda r: in_window(r["start_date"], start, end), axis=1)]
    closed_won = df[
        (df["status"] == STATUS_WON)
        & df.apply(lambda r: in_window(r["close_at"], start, end), axis=1)
    ]
    closed_lost = df[
        (df["status"] == STATUS_LOST)
        & df.apply(lambda r: in_window(r["close_at"], start, end), axis=1)
    ]
    paused = df[
        (df["status"] == STATUS_ON_HOLD)
        & df.apply(lambda r: is_open_at(r, end - pd.Timedelta(seconds=1)) or in_window(r["close_at"], start, end), axis=1)
    ]
    remaining_open = df[
        df.apply(lambda r: is_open_at(r, end - pd.Timedelta(seconds=1)) and r["status"] == STATUS_ACTIVE, axis=1)
    ]

    beginning_total = len(carry_over)
    fill_rate = (len(closed_won) / beginning_total) if beginning_total else 0.0

    return {
        "carry_over": carry_over,
        "newly_opened": newly_opened,
        "total_open": total_open,
        "in_offer": in_offer,
        "offer_accepted": offer_accepted,
        "started": started,
        "closed_won": closed_won,
        "closed_lost": closed_lost,
        "paused": paused,
        "remaining_open": remaining_open,
        "beginning_total": beginning_total,
        "fill_rate": fill_rate,
    }
