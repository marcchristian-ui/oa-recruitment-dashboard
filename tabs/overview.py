import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from manatal.constants import FILL_RATE_TARGET
from manatal.transforms import funnel_metrics, month_window


def _kpi(col, label, value, sub=None, color=None):
    col.markdown(
        f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:12px;padding:14px;">
          <div style="color:#94a3b8;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;">{label}</div>
          <div style="color:{color or '#f1f5f9'};font-size:28px;font-weight:700;line-height:1.1;margin-top:4px;">{value}</div>
          {f'<div style="color:#94a3b8;font-size:12px;margin-top:4px;">{sub}</div>' if sub else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _funnel_chart(metrics: dict) -> go.Figure:
    stages = [
        ("Beginning Open", metrics["beginning_total"]),
        ("Newly Opened", len(metrics["newly_opened"])),
        ("Total Open", len(metrics["total_open"])),
        ("In Offer", len(metrics["in_offer"])),
        ("Offer Accepted", len(metrics["offer_accepted"])),
        ("Started", len(metrics["started"])),
        ("Closed Won", len(metrics["closed_won"])),
    ]
    fig = go.Figure(
        go.Funnel(
            y=[s[0] for s in stages],
            x=[s[1] for s in stages],
            textposition="inside",
            textinfo="value+percent initial",
            marker={"color": ["#3b82f6", "#60a5fa", "#0ea5e9", "#06b6d4", "#14b8a6", "#22c55e", "#16a34a"]},
        )
    )
    fig.update_layout(
        height=420,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
        font_color="#e2e8f0",
    )
    return fig


def _mom_trend(df: pd.DataFrame, year: int, month: int) -> go.Figure:
    months = []
    closed_won = []
    opened = []
    for offset in range(5, -1, -1):
        m_year, m_month = year, month - offset
        while m_month <= 0:
            m_month += 12
            m_year -= 1
        m = funnel_metrics(df, m_year, m_month)
        label = f"{m_year}-{m_month:02d}"
        months.append(label)
        closed_won.append(len(m["closed_won"]))
        opened.append(len(m["newly_opened"]))

    fig = go.Figure()
    fig.add_trace(go.Bar(x=months, y=opened, name="Newly Opened", marker_color="#3b82f6"))
    fig.add_trace(go.Bar(x=months, y=closed_won, name="Closed Won", marker_color="#22c55e"))
    fig.update_layout(
        barmode="group",
        height=320,
        margin=dict(l=10, r=10, t=20, b=10),
        paper_bgcolor="#0b1220",
        plot_bgcolor="#0b1220",
        font_color="#e2e8f0",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def render(df: pd.DataFrame, year: int, month: int):
    metrics = funnel_metrics(df, year, month)
    start, end = month_window(year, month)
    fill_rate = metrics["fill_rate"]

    st.subheader(f"Recruitment Funnel — {start.strftime('%B %Y')}")

    cols = st.columns(4)
    _kpi(cols[0], "Beginning Open Roles", metrics["beginning_total"],
         "Carry-over from prior months")
    _kpi(cols[1], "Newly Opened", len(metrics["newly_opened"]),
         "Opened within selected month")
    _kpi(cols[2], "Total Open for Month", len(metrics["total_open"]),
         "Beginning + newly opened")
    fr_color = "#22c55e" if fill_rate >= FILL_RATE_TARGET else "#ef4444"
    _kpi(cols[3], f"Fill Rate (target {int(FILL_RATE_TARGET*100)}%)",
         f"{fill_rate*100:.1f}%",
         f"{len(metrics['closed_won'])} won ÷ {metrics['beginning_total']} beginning",
         color=fr_color)

    cols = st.columns(4)
    _kpi(cols[0], "In Offer Stage", len(metrics["in_offer"]))
    _kpi(cols[1], "Offer Accepted", len(metrics["offer_accepted"]))
    _kpi(cols[2], "Started / Filled", len(metrics["started"]))
    _kpi(cols[3], "Paused / On-Hold", len(metrics["paused"]))

    cols = st.columns(4)
    _kpi(cols[0], "Closed Won", len(metrics["closed_won"]))
    _kpi(cols[1], "Closed Lost", len(metrics["closed_lost"]))
    _kpi(cols[2], "Remaining Open", len(metrics["remaining_open"]))
    _kpi(cols[3], "Total Headcount Requested", int(metrics["total_open"]["headcount"].sum() if not metrics["total_open"].empty else 0))

    st.markdown("### Recruitment Funnel")
    st.plotly_chart(_funnel_chart(metrics), use_container_width=True)

    st.markdown("### 6-Month Trend")
    st.plotly_chart(_mom_trend(df, year, month), use_container_width=True)
