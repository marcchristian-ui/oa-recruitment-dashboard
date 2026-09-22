import pandas as pd
import plotly.express as px
import streamlit as st

from manatal.constants import STATUS_WON
from manatal.transforms import month_window, in_window


def render(df: pd.DataFrame, year: int, month: int):
    start, end = month_window(year, month)
    won = df[
        (df["status"] == STATUS_WON)
        & df.apply(lambda r: in_window(r["close_at"], start, end), axis=1)
    ].copy()

    started = df[df.apply(lambda r: in_window(r["start_date"], start, end), axis=1)].copy()
    offer_accepted = df[
        df.apply(lambda r: in_window(r["offer_acceptance_date"], start, end), axis=1)
    ].copy()
    # roles with offer accepted in month but start date in future
    future_starts = offer_accepted[
        offer_accepted["start_date"].notna() & (offer_accepted["start_date"] >= end)
    ]

    st.subheader(f"Closed Won — {start.strftime('%B %Y')}")
    cols = st.columns(4)
    cols[0].metric("Closed Won (Total)", len(won))
    cols[1].metric("Started (this month)", len(started))
    cols[2].metric("Offer Accepted (future start)", len(future_starts))
    cols[3].metric("Total Headcount Filled", int(won["headcount"].sum() or 0))

    st.markdown("### Stage Breakdown")
    if won.empty:
        st.info("No closed-won roles in this month.")
    else:
        breakdown = pd.DataFrame({
            "stage": ["Started", "Offer Accepted (future start)", "Other Closed Won"],
            "count": [
                len(started),
                len(future_starts),
                max(0, len(won) - len(started) - len(future_starts)),
            ],
        })
        fig = px.bar(breakdown, x="stage", y="count", color="stage",
                     color_discrete_sequence=["#22c55e", "#06b6d4", "#64748b"])
        fig.update_layout(height=280, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                          font_color="#e2e8f0", showlegend=False,
                          margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### Started Roles")
    if started.empty:
        st.info("No roles started in this month.")
    else:
        st.dataframe(
            started[["client_name", "position_name", "start_date", "role_type"]]
            .rename(columns={
                "client_name": "Client",
                "position_name": "Role Title",
                "start_date": "Start Date",
                "role_type": "Type",
            })
            .sort_values("Start Date"),
            use_container_width=True, hide_index=True,
        )

    st.markdown("### All Closed Won (Detailed)")
    if won.empty:
        return
    won["type_full"] = won.apply(
        lambda r: r["role_type"] if r["role_type"] == "New Logo" else f"Organic — {r['organic_subtype'] or '?'}",
        axis=1,
    )
    show = won[[
        "headcount", "client_name", "position_name", "start_date",
        "offer_acceptance_date", "close_at", "type_full"
    ]].rename(columns={
        "headcount": "HC Requested",
        "client_name": "Client",
        "position_name": "Role Title",
        "start_date": "Start Date",
        "offer_acceptance_date": "Offer Accepted",
        "close_at": "Closed Date",
        "type_full": "Type",
    }).sort_values("Closed Date", ascending=False)
    st.dataframe(show, use_container_width=True, hide_index=True)

    st.markdown("### 6-Month Hires Trend")
    months = []
    counts = []
    for offset in range(5, -1, -1):
        my, mm = year, month - offset
        while mm <= 0:
            mm += 12
            my -= 1
        s, e = month_window(my, mm)
        c = df[(df["status"] == STATUS_WON) & df["close_at"].between(s, e - pd.Timedelta(seconds=1))]
        months.append(f"{my}-{mm:02d}")
        counts.append(len(c))
    trend = pd.DataFrame({"month": months, "closed_won": counts})
    fig = px.line(trend, x="month", y="closed_won", markers=True,
                  color_discrete_sequence=["#22c55e"])
    fig.update_layout(height=280, paper_bgcolor="#0b1220", plot_bgcolor="#0b1220",
                      font_color="#e2e8f0", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)
