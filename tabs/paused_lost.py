import pandas as pd
import plotly.express as px
import streamlit as st

from manatal.constants import STATUS_ON_HOLD, STATUS_LOST
from manatal.transforms import month_window, in_window


def render(df: pd.DataFrame, year: int, month: int):
    start, end = month_window(year, month)

    paused = df[df["status"] == STATUS_ON_HOLD].copy()
    lost_in_month = df[
        (df["status"] == STATUS_LOST)
        & df.apply(lambda r: in_window(r["close_at"], start, end), axis=1)
    ].copy()

    now = pd.Timestamp.utcnow().tz_convert(None) if pd.Timestamp.utcnow().tzinfo else pd.Timestamp.utcnow()
    paused["paused_date"] = paused["close_at"].fillna(paused["updated_at"])
    paused["days_paused"] = (now - paused["paused_date"]).dt.days.clip(lower=0)

    st.subheader("Paused & Closed Lost Roles")
    cols = st.columns(5)
    cols[0].metric("Total Paused", len(paused))
    cols[1].metric("Closed Lost (this month)", len(lost_in_month))
    cols[2].metric("Total HC Paused", int(paused["headcount"].sum() or 0))
    cols[3].metric("New Logo Paused", int((paused["role_type"] == "New Logo").sum()))
    cols[4].metric("Organic Paused", int((paused["role_type"] == "Organic").sum()))

    st.markdown("### Breakdown by Type")
    type_data = pd.DataFrame({
        "category": ["Paused — New Logo", "Paused — Organic", "Closed Lost — New Logo", "Closed Lost — Organic"],
        "count": [
            int((paused["role_type"] == "New Logo").sum()),
            int((paused["role_type"] == "Organic").sum()),
            int((lost_in_month["role_type"] == "New Logo").sum()),
            int((lost_in_month["role_type"] == "Organic").sum()),
        ],
    })
    fig = px.bar(type_data, x="category", y="count", color="category",
                 color_discrete_sequence=["#f59e0b", "#fbbf24", "#ef4444", "#f87171"])
    fig.update_layout(height=300, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                      font_color="#e2e8f0", showlegend=False,
                      margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Pause Reason Distribution")
    if not paused.empty:
        reason_counts = paused["pause_reason"].value_counts().reset_index()
        reason_counts.columns = ["reason", "count"]
        fig = px.bar(reason_counts, x="count", y="reason", orientation="h",
                     color_discrete_sequence=["#f59e0b"])
        fig.update_layout(height=320, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                          font_color="#e2e8f0", margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Paused Roles — Detail")
    if paused.empty:
        st.info("No paused roles.")
    else:
        paused["type_full"] = paused.apply(
            lambda r: r["role_type"] if r["role_type"] == "New Logo" else f"Organic — {r['organic_subtype'] or '?'}",
            axis=1,
        )
        show = paused[[
            "headcount", "client_name", "position_name", "paused_date",
            "pause_reason", "type_full", "days_paused", "remarks_text"
        ]].rename(columns={
            "headcount": "HC",
            "client_name": "Client",
            "position_name": "Role Title",
            "paused_date": "Paused Date",
            "pause_reason": "Reason",
            "type_full": "Type",
            "days_paused": "Days Paused",
            "remarks_text": "Notes",
        }).sort_values("Days Paused", ascending=False)
        st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("### Closed Lost — Detail")
    if lost_in_month.empty:
        st.info("No roles closed lost in this month.")
    else:
        lost_in_month["type_full"] = lost_in_month.apply(
            lambda r: r["role_type"] if r["role_type"] == "New Logo" else f"Organic — {r['organic_subtype'] or '?'}",
            axis=1,
        )
        show = lost_in_month[[
            "headcount", "client_name", "position_name", "close_at",
            "type_full", "remarks_text"
        ]].rename(columns={
            "headcount": "HC",
            "client_name": "Client",
            "position_name": "Role Title",
            "close_at": "Lost Date",
            "type_full": "Type",
            "remarks_text": "Notes",
        }).sort_values("Lost Date", ascending=False)
        st.dataframe(show, use_container_width=True, hide_index=True)
