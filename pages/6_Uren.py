"""Uren & Bezetting — Time tracking and utilization."""
from __future__ import annotations

from datetime import date, timedelta
from calendar import monthrange

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_time_entries, get_people, get_projects, build_lookup, safe_load

st.markdown("# Uren & Bezetting")

today = date.today()

# ── Sidebar: month selector ──
MONTH_NAMES = ["Januari", "Februari", "Maart", "April", "Mei", "Juni",
               "Juli", "Augustus", "September", "Oktober", "November", "December"]
month_options = []
for i in range(6):
    d = today.replace(day=1) - timedelta(days=i * 28)
    d = d.replace(day=1)
    label = f"{MONTH_NAMES[d.month - 1]} {d.year}"
    month_options.append((label, d.year, d.month))

with st.sidebar:
    st.markdown("### Maand")
    selected_label = st.selectbox(
        "Selecteer maand",
        [opt[0] for opt in month_options],
        index=0,
        key="uren_month",
    )
    sel_idx = [opt[0] for opt in month_options].index(selected_label)
    sel_year = month_options[sel_idx][1]
    sel_month = month_options[sel_idx][2]

month_start = date(sel_year, sel_month, 1)
_, month_days = monthrange(sel_year, sel_month)
month_end = date(sel_year, sel_month, month_days)
# For data query, cap end date at today if viewing current month
query_end = min(month_end, today)
week_start = today - timedelta(days=today.weekday())

people = safe_load(get_people)
projects = safe_load(get_projects)
people_lookup = build_lookup(people)
project_lookup = build_lookup(projects)

time_month = safe_load(get_time_entries, after=month_start.isoformat(), before=query_end.isoformat())

if time_month:
    df = pd.DataFrame(time_month)
    df["hours"] = df["minutes"] / 60
    df["person"] = df["person_id"].map(people_lookup).fillna("Onbekend")
    df["project"] = df["project_id"].map(project_lookup).fillna("Onbekend")

    total_hours = df["hours"].sum()
    billable_hours = df[df["billable"]]["hours"].sum()
    util_rate = (billable_hours / total_hours * 100) if total_hours > 0 else 0

    working_days_elapsed = sum(1 for d in pd.date_range(month_start, query_end) if d.weekday() < 5)
    working_days_total = sum(1 for d in pd.date_range(month_start, month_end) if d.weekday() < 5)

    # KPIs
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Uren deze maand", f"{total_hours:.1f}")
    with c2:
        st.metric("Billable", f"{billable_hours:.1f}")
    with c3:
        color = "inverse" if util_rate < 70 else "normal"
        st.metric("Billable %", f"{util_rate:.0f}%",
                  delta="Target: 70%" if util_rate < 70 else "Op target",
                  delta_color=color)
    with c4:
        st.metric("Werkdagen", f"{working_days_elapsed}/{working_days_total}")

    # Per person
    st.divider()
    st.markdown("#### Per Persoon")
    person_df = df.groupby("person").agg(
        Totaal=("hours", "sum"),
        Billable=("hours", lambda x: x[df.loc[x.index, "billable"]].sum()),
    ).reset_index()
    person_df["Util %"] = (person_df["Billable"] / person_df["Totaal"] * 100).fillna(0)
    person_df = person_df.sort_values("Totaal", ascending=False)

    for _, row in person_df.iterrows():
        c_a, c_b, c_c = st.columns([2, 2, 1])
        with c_a:
            st.markdown(f"**{row['person']}**")
        with c_b:
            st.markdown(f"{row['Totaal']:.1f}u totaal, {row['Billable']:.1f}u billable")
        with c_c:
            pct = row["Util %"]
            clr = "red" if pct < 50 else "orange" if pct < 70 else "green"
            st.markdown(f":{clr}[{pct:.0f}%]")

    # Per project
    st.divider()
    st.markdown("#### Per Project")
    proj_df = df.groupby("project")["hours"].sum().sort_values(ascending=False).reset_index()
    proj_df.columns = ["Project", "Uren"]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=proj_df["Project"], y=proj_df["Uren"],
        marker_color="#003566",
        text=proj_df["Uren"].apply(lambda x: f"{x:.1f}u"),
        textposition="outside",
    ))
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Weekly trend
    st.divider()
    st.markdown("#### Weektrend (laatste 8 weken)")
    eight_weeks_ago = today - timedelta(weeks=8)
    time_8w = safe_load(get_time_entries, after=eight_weeks_ago.isoformat(), before=today.isoformat())
    if time_8w:
        wdf = pd.DataFrame(time_8w)
        wdf["hours"] = wdf["minutes"] / 60
        wdf["week"] = pd.to_datetime(wdf["date"]).dt.isocalendar().week
        weekly = wdf.groupby("week").agg(
            Totaal=("hours", "sum"),
            Billable=("hours", lambda x: x[wdf.loc[x.index, "billable"]].sum()),
        ).reset_index()
        weekly["week_label"] = "W" + weekly["week"].astype(str)

        fig_w = go.Figure()
        fig_w.add_trace(go.Bar(
            x=weekly["week_label"], y=weekly["Totaal"],
            name="Totaal", marker_color="#86868B",
        ))
        fig_w.add_trace(go.Bar(
            x=weekly["week_label"], y=weekly["Billable"],
            name="Billable", marker_color="#003566",
        ))
        fig_w.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=0),
            barmode="overlay", template="plotly_white",
            legend=dict(orientation="h", y=1.1),
        )
        st.plotly_chart(fig_w, use_container_width=True)
else:
    st.warning("Geen uren geboekt deze maand.")
