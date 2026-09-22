import pandas as pd
import plotly.express as px
import streamlit as st

from manatal.constants import AGING_COLORS, STATUS_ACTIVE
from manatal.transforms import aging_bucket


def _currently_open(df: pd.DataFrame) -> pd.DataFrame:
    open_df = df[df["status"] == STATUS_ACTIVE].copy()
    now = pd.Timestamp.utcnow().tz_convert(None) if pd.Timestamp.utcnow().tzinfo else pd.Timestamp.utcnow()
    open_df["days_open"] = (now - open_df["open_at"]).dt.days
    open_df["aging"] = open_df["days_open"].apply(aging_bucket)
    return open_df


def _section(title: str, sub: pd.DataFrame):
    avg = sub["days_open"].mean() if not sub.empty else 0
    st.markdown(f"#### {title}")
    cols = st.columns(5)
    cols[0].metric("Avg Days Open", f"{avg:.1f}" if not sub.empty else "—")
    bucket_counts = sub["aging"].value_counts().to_dict() if not sub.empty else {}
    for i, label in enumerate(["Fresh", "Normal", "Aging", "Critical"], start=1):
        cols[i].metric(label, bucket_counts.get(label, 0))

    if sub.empty:
        return
    by_bucket = sub.groupby("aging")["id"].count().reindex(
        ["Fresh", "Normal", "Aging", "Critical"], fill_value=0
    ).reset_index(name="count")
    fig = px.bar(
        by_bucket, x="aging", y="count", color="aging",
        color_discrete_map=AGING_COLORS,
    )
    fig.update_layout(
        height=240, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
        font_color="#e2e8f0", showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)


def render(df: pd.DataFrame, year: int, month: int):
    open_df = _currently_open(df)

    st.subheader("Open Role Aging")
    st.caption("Fresh: 0–14 days · Normal: 15–30 · Aging: 31–45 · Critical: 46+")

    if open_df.empty:
        st.info("No currently-open roles.")
        return

    new_logo = open_df[open_df["role_type"] == "New Logo"]
    ramp = open_df[(open_df["role_type"] == "Organic") & (open_df["organic_subtype"] == "Ramp")]
    backfill = open_df[(open_df["role_type"] == "Organic") & (open_df["organic_subtype"] == "Backfill")]

    _section("A. New Logo Roles", new_logo)
    _section("B. Organic Roles — Ramp", ramp)
    _section("C. Organic Roles — Backfill", backfill)

    st.markdown("### All Currently Open Roles")
    show = open_df.assign(
        type_full=lambda d: d.apply(
            lambda r: r["role_type"] if r["role_type"] == "New Logo" else f"Organic — {r['organic_subtype'] or '?'}",
            axis=1,
        )
    )[
        ["headcount", "position_name", "client_name", "type_full", "open_at", "days_open", "aging", "status"]
    ].rename(columns={
        "headcount": "HC Requested",
        "position_name": "Role Title",
        "client_name": "Client",
        "type_full": "Type",
        "open_at": "Open Date",
        "days_open": "Days Open",
        "aging": "Aging",
        "status": "Status",
    }).sort_values("Days Open", ascending=False)

    st.dataframe(show, use_container_width=True, hide_index=True)
