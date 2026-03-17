"""Maandreview — Monthly deep-dive dashboard."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from calendar import monthrange

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import (
    get_invoices, get_time_entries, get_deals, get_people, get_projects,
    get_companies, get_budgets, build_lookup,
)
from services.bank_api import is_configured as bank_configured, get_balance, get_transactions

# ── Colors ──
CLR_PRIMARY = "#003566"
CLR_RED = "#E63946"
CLR_ORANGE = "#F4A261"
CLR_GREEN = "#2A9D8F"
CLR_GREY = "#86868B"

st.markdown("# Maandreview")
st.caption("Maandelijkse deep-dive: financieel, uren, pipeline en budget.")

today = date.today()
current_month = today.month - 1  # 0-indexed
year_start = today.replace(month=1, day=1)

# ── Load all data ──
with st.spinner("Data ophalen..."):
    invoices = get_invoices()
    people = get_people()
    projects = get_projects()
    companies = get_companies()
    deals = get_deals()
    budgets = get_budgets()

people_lookup = build_lookup(people)
project_lookup = build_lookup(projects)
company_lookup = build_lookup(companies)

# ── Cost plan ──
COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
cost_plan = {"categories": {}, "one_offs": []}
if COST_FILE.exists():
    cost_plan = json.loads(COST_FILE.read_text(encoding="utf-8"))

monthly_plan_costs = []
for m_idx in range(12):
    recurring = sum(vals[m_idx] for vals in cost_plan.get("categories", {}).values())
    oneoff = sum(oo["amount"] for oo in cost_plan.get("one_offs", []) if oo["month"] == m_idx)
    monthly_plan_costs.append(recurring + oneoff)

# ── Invoice / revenue data ──
paid_invoices = [i for i in invoices if i["status"] == "paid" and i.get("paid_date")]
sent_invoices = [i for i in invoices if i["status"] in ("sent", "overdue")]
total_outstanding = sum(i["total_with_tax"] for i in sent_invoices)

# Revenue this month
month_start_str = today.replace(day=1).isoformat()
month_end_str = today.isoformat()
prev_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
prev_month_end = today.replace(day=1) - timedelta(days=1)

rev_this_month = sum(
    i["total_with_tax"] for i in paid_invoices
    if (i.get("paid_date") or "") >= month_start_str
)
rev_last_month = sum(
    i["total_with_tax"] for i in paid_invoices
    if prev_month_start.isoformat() <= (i.get("paid_date") or "") <= prev_month_end.isoformat()
)
rev_ytd = sum(
    i["total_with_tax"] for i in paid_invoices
    if (i.get("paid_date") or "") >= year_start.isoformat()
)
rev_avg = rev_ytd / max(today.month, 1)

# Bank balance
if bank_configured():
    balance_data = get_balance()
    bank_balance = balance_data["amount"] if balance_data else None
else:
    bank_balance = None

# Actual expenses this month (from bank)
actual_expenses_month = 0
if bank_configured():
    days_into_month = (today - today.replace(day=1)).days + 1
    transactions = get_transactions(days=days_into_month + 5)
    if transactions:
        month_txs = [t for t in transactions if t["date"] >= month_start_str and t["amount"] < 0]
        actual_expenses_month = sum(abs(t["amount"]) for t in month_txs)

# Planned expenses this month
planned_expenses_month = monthly_plan_costs[current_month] if current_month < len(monthly_plan_costs) else 0

# Net profit/loss
net_this_month = rev_this_month - actual_expenses_month if actual_expenses_month > 0 else rev_this_month - planned_expenses_month

# Runway
runway_months = None
if bank_balance and any(c > 0 for c in monthly_plan_costs):
    bal = bank_balance
    outstanding_pool = total_outstanding
    runway_months = 0
    for offset in range(24):
        m_idx = (current_month + offset) % 12
        cost = monthly_plan_costs[m_idx]
        income = outstanding_pool / 2 if offset < 2 and outstanding_pool > 0 else 0
        if offset < 2:
            outstanding_pool = max(0, outstanding_pool - income)
        bal = bal - cost + income
        if bal <= 0:
            break
        runway_months += 1

# ══════════════════════════════════════════════════════════════
# ROW 1: FINANCIAL SUMMARY
# ══════════════════════════════════════════════════════════════

st.markdown("#### Financieel overzicht")

c1, c2, c3, c4 = st.columns(4)
with c1:
    delta_rev = None
    if rev_last_month > 0:
        pct_change = ((rev_this_month - rev_last_month) / rev_last_month) * 100
        delta_rev = f"{pct_change:+.0f}% vs vorige maand"
    st.metric("Omzet deze maand", f"EUR {rev_this_month:,.0f}", delta=delta_rev)
with c2:
    expense_label = f"EUR {actual_expenses_month:,.0f}" if actual_expenses_month > 0 else f"EUR {planned_expenses_month:,.0f}"
    expense_delta = None
    if actual_expenses_month > 0 and planned_expenses_month > 0:
        diff = actual_expenses_month - planned_expenses_month
        expense_delta = f"EUR {diff:+,.0f} vs plan"
    st.metric(
        "Uitgaven deze maand" if actual_expenses_month > 0 else "Kosten (plan)",
        expense_label,
        delta=expense_delta,
        delta_color="inverse" if (expense_delta and diff > 0) else "normal",
    )
with c3:
    net_color = "normal" if net_this_month >= 0 else "inverse"
    st.metric("Netto resultaat", f"EUR {net_this_month:,.0f}",
              delta="Positief" if net_this_month >= 0 else "Negatief",
              delta_color=net_color)
with c4:
    if runway_months is not None:
        if runway_months >= 12:
            st.metric("Runway", f"{runway_months}+ mnd", delta="Gezond", delta_color="normal")
        elif runway_months >= 6:
            st.metric("Runway", f"{runway_months} mnd", delta="OK", delta_color="normal")
        elif runway_months >= 3:
            st.metric("Runway", f"{runway_months} mnd", delta="Aandacht", delta_color="off")
        else:
            st.metric("Runway", f"{runway_months} mnd", delta="Kritiek", delta_color="inverse")
    else:
        st.metric("Runway", "—")

# ══════════════════════════════════════════════════════════════
# ROW 2: OMZET TREND — bar chart last 6 months
# ══════════════════════════════════════════════════════════════

st.markdown("#### Omzet trend")

if paid_invoices:
    rev_df = pd.DataFrame(paid_invoices)
    rev_df["month"] = pd.to_datetime(rev_df["paid_date"]).dt.to_period("M").astype(str)
    monthly_rev = rev_df.groupby("month")["total_with_tax"].sum().reset_index()
    monthly_rev.columns = ["Maand", "Omzet"]
    monthly_rev = monthly_rev.tail(6)

    # Break-even line from cost plan
    break_even = planned_expenses_month if planned_expenses_month > 0 else 10500

    fig_rev = go.Figure()
    fig_rev.add_trace(go.Bar(
        x=monthly_rev["Maand"], y=monthly_rev["Omzet"],
        marker_color=CLR_PRIMARY,
        text=monthly_rev["Omzet"].apply(lambda x: f"EUR {x:,.0f}"),
        textposition="outside",
    ))
    fig_rev.add_hline(y=break_even, line_dash="dash", line_color=CLR_RED,
                      annotation_text=f"Break-even: EUR {break_even:,.0f}")
    fig_rev.update_layout(
        height=320, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="EUR", template="plotly_white",
    )
    st.plotly_chart(fig_rev, use_container_width=True)
else:
    st.info("Geen betaalde facturen gevonden.")

# ══════════════════════════════════════════════════════════════
# ROW 3: UREN TREND
# ══════════════════════════════════════════════════════════════

st.markdown("#### Uren trend")

col_chart, col_util = st.columns([2, 1], gap="large")

with col_chart:
    # Weekly billable vs total — last 8 weeks
    eight_weeks_ago = today - timedelta(weeks=8)
    time_8w = get_time_entries(after=eight_weeks_ago.isoformat(), before=today.isoformat())

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
            name="Totaal", marker_color=CLR_GREY,
        ))
        fig_w.add_trace(go.Bar(
            x=weekly["week_label"], y=weekly["Billable"],
            name="Billable", marker_color=CLR_PRIMARY,
        ))
        fig_w.update_layout(
            height=300, margin=dict(l=0, r=0, t=10, b=0),
            barmode="overlay", template="plotly_white",
            legend=dict(orientation="h", y=1.1),
            yaxis_title="Uren",
        )
        st.plotly_chart(fig_w, use_container_width=True)
    else:
        st.info("Geen uren gevonden voor de afgelopen 8 weken.")

with col_util:
    # Utilization % per person this month
    st.markdown("##### Bezetting deze maand")
    month_start = today.replace(day=1)
    _, month_days = monthrange(today.year, today.month)
    month_end = date(today.year, today.month, month_days)
    query_end = min(month_end, today)

    time_month = get_time_entries(after=month_start.isoformat(), before=query_end.isoformat())
    if time_month:
        mdf = pd.DataFrame(time_month)
        mdf["hours"] = mdf["minutes"] / 60
        mdf["person"] = mdf["person_id"].map(people_lookup).fillna("Onbekend")

        person_df = mdf.groupby("person").agg(
            Totaal=("hours", "sum"),
            Billable=("hours", lambda x: x[mdf.loc[x.index, "billable"]].sum()),
        ).reset_index()
        person_df["Util %"] = (person_df["Billable"] / person_df["Totaal"] * 100).fillna(0)

        for _, row in person_df.iterrows():
            pct = row["Util %"]
            clr = "inverse" if pct < 50 else "off" if pct < 70 else "normal"
            st.metric(
                row["person"],
                f"{row['Totaal']:.0f}u totaal",
                delta=f"{pct:.0f}% billable",
                delta_color=clr,
            )
    else:
        st.info("Geen uren deze maand.")

# ══════════════════════════════════════════════════════════════
# ROW 4: PIPELINE HEALTH
# ══════════════════════════════════════════════════════════════

st.markdown("#### Pipeline health")

open_deals = [d for d in deals if not d.get("closed")]

if open_deals:
    deals_df = pd.DataFrame(open_deals)
    deals_df["company"] = deals_df["company_id"].map(company_lookup).fillna("")

    col_pipe_chart, col_stale = st.columns([2, 1], gap="large")

    with col_pipe_chart:
        # Deals by stage — weighted revenue
        stage_df = deals_df.groupby("status").agg(
            Aantal=("id", "count"),
            Gewogen=("weighted_value", "sum"),
        ).reset_index().sort_values("Gewogen", ascending=True)

        fig_stage = go.Figure()
        fig_stage.add_trace(go.Bar(
            y=stage_df["status"], x=stage_df["Gewogen"],
            orientation="h",
            marker_color=CLR_PRIMARY,
            text=stage_df.apply(
                lambda r: f"EUR {r['Gewogen']:,.0f} ({r['Aantal']} deals)", axis=1
            ),
            textposition="outside",
        ))
        fig_stage.update_layout(
            height=max(200, len(stage_df) * 50),
            margin=dict(l=0, r=120, t=10, b=0),
            xaxis_title="EUR (gewogen)",
            template="plotly_white",
        )
        st.plotly_chart(fig_stage, use_container_width=True)

    with col_stale:
        # Stale deals — no activity >2 weeks
        st.markdown("##### Stale deals")
        st.caption("Geen activiteit >2 weken")

        two_weeks_ago = (today - timedelta(days=14)).isoformat()
        stale = deals_df[
            (deals_df["date"].fillna("") < two_weeks_ago) | (deals_df["date"].isna())
        ]

        if not stale.empty:
            for _, deal in stale.iterrows():
                st.warning(
                    f"**{deal['company']}** — {deal['name']} ({deal['status']})",
                    icon=":material/schedule:",
                )
        else:
            st.success("Alle deals recent bijgewerkt.", icon=":material/check_circle:")
else:
    st.info("Geen open deals.")

# ══════════════════════════════════════════════════════════════
# ROW 5: BUDGET BURN
# ══════════════════════════════════════════════════════════════

st.markdown("#### Budget burn per project")

active_budgets = [b for b in budgets if b["total_hours"] > 0]
if active_budgets:
    bdf = pd.DataFrame(active_budgets)
    bdf["project"] = bdf["project_id"].map(project_lookup).fillna("Onbekend")
    bdf["burn_pct"] = (bdf["spent_hours"] / bdf["total_hours"] * 100).clip(0, 150)
    bdf = bdf.sort_values("burn_pct", ascending=True)

    fig_burn = go.Figure()
    fig_burn.add_trace(go.Bar(
        y=bdf["name"], x=bdf["burn_pct"],
        orientation="h",
        marker_color=bdf["burn_pct"].apply(
            lambda x: CLR_RED if x > 90 else CLR_ORANGE if x > 70 else CLR_PRIMARY
        ),
        text=bdf.apply(
            lambda r: f"{r['spent_hours']:.0f}/{r['total_hours']:.0f}u ({r['burn_pct']:.0f}%)",
            axis=1,
        ),
        textposition="outside",
    ))
    fig_burn.add_vline(x=100, line_dash="dash", line_color=CLR_RED)
    fig_burn.update_layout(
        height=max(250, len(active_budgets) * 40),
        margin=dict(l=0, r=100, t=10, b=0),
        xaxis_title="Budget verbruikt (%)", template="plotly_white",
    )
    st.plotly_chart(fig_burn, use_container_width=True)
else:
    st.info("Geen budgetten met uren gevonden.")
