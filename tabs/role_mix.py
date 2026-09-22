import pandas as pd
import plotly.express as px
import streamlit as st

from manatal.transforms import month_window


def _open_during_month(df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    start, end = month_window(year, month)
    mask = df["open_at"].notna() & (df["open_at"] < end) & (
        df["close_at"].isna() | (df["close_at"] >= start)
    )
    return df[mask].copy()


def _aging_now(row, now):
    if pd.isna(row["open_at"]):
        return None
    end = row["close_at"] if pd.notna(row["close_at"]) else now
    return max(0, (end - row["open_at"]).days)


def render(df: pd.DataFrame, year: int, month: int):
    scoped = _open_during_month(df, year, month)
    now = pd.Timestamp.utcnow().tz_convert(None) if pd.Timestamp.utcnow().tzinfo else pd.Timestamp.utcnow()
    scoped["days_open"] = scoped.apply(lambda r: _aging_now(r, now), axis=1)

    new_logo = scoped[scoped["role_type"] == "New Logo"]
    organic = scoped[scoped["role_type"] == "Organic"]

    cols = st.columns(4)
    cols[0].metric("New Logo Roles", len(new_logo), f"{int(new_logo['headcount'].sum() or 0)} HC requested")
    cols[1].metric("Organic Roles", len(organic), f"{int(organic['headcount'].sum() or 0)} HC requested")
    cols[2].metric("Ramp", int((organic["organic_subtype"] == "Ramp").sum()))
    cols[3].metric("Backfill", int((organic["organic_subtype"] == "Backfill").sum()))

    st.markdown("### New Logo vs Organic")
    counts = (
        scoped.groupby("role_type")["id"].count().reset_index(name="count")
    )
    if not counts.empty:
        fig = px.pie(counts, names="role_type", values="count", hole=0.5,
                     color_discrete_map={"New Logo": "#0ea5e9", "Organic": "#22c55e"})
        fig.update_layout(height=320, paper_bgcolor="#0b1220", font_color="#e2e8f0",
                          margin=dict(l=10, r=10, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("### A. New Logo Roles")
    if new_logo.empty:
        st.info("No New Logo roles in scope for this month.")
    else:
        st.dataframe(
            new_logo[["headcount", "position_name", "client_name", "open_at", "days_open", "status"]]
            .rename(columns={
                "headcount": "HC Requested",
                "position_name": "Role Title",
                "client_name": "Client",
                "open_at": "Open Date",
                "days_open": "Days Open",
                "status": "Status",
            })
            .sort_values("Days Open", ascending=False),
            use_container_width=True, hide_index=True,
        )

    st.markdown("### B. Organic Roles")
    if organic.empty:
        st.info("No Organic roles in scope for this month.")
    else:
        st.dataframe(
            organic[["headcount", "position_name", "client_name", "organic_subtype", "open_at", "days_open", "status"]]
            .rename(columns={
                "headcount": "HC Requested",
                "position_name": "Role Title",
                "client_name": "Client",
                "organic_subtype": "Type",
                "open_at": "Open Date",
                "days_open": "Days Open",
                "status": "Status",
            })
            .sort_values("Days Open", ascending=False),
            use_container_width=True, hide_index=True,
        )
