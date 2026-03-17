"""Weekstart — One-screen overview for the Monday check-in with Joris."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import (
    get_invoices, get_time_entries, get_deals, get_people, get_projects,
    get_companies, build_lookup,
)
from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Weekstart")
st.caption("Alles wat je nodig hebt voor de maandag check-in — in één scherm.")

today = date.today()
current_month = today.month - 1
year_start = today.replace(month=1, day=1)
last_week_start = today - timedelta(days=today.weekday() + 7)
last_week_end = last_week_start + timedelta(days=6)
this_week_start = today - timedelta(days=today.weekday())

# ── Load all data ──
with st.spinner("Data ophalen..."):
    invoices = get_invoices()
    people = get_people()
    projects = get_projects()
    companies = get_companies()
    deals = get_deals()
    time_last_week = get_time_entries(
        after=last_week_start.isoformat(),
        before=last_week_end.isoformat(),
    )

people_lookup = build_lookup(people)
project_lookup = build_lookup(projects)
company_lookup = build_lookup(companies)

# Bank balance
if bank_configured():
    balance_data = get_balance()
    bank_balance = balance_data["amount"] if balance_data else None
else:
    bank_balance = None

# Cost plan
COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
monthly_cost = 0
if COST_FILE.exists():
    plan = json.loads(COST_FILE.read_text(encoding="utf-8"))
    monthly_cost = sum(vals[current_month] for vals in plan.get("categories", {}).values())
    monthly_cost += sum(oo["amount"] for oo in plan.get("one_offs", []) if oo["month"] == current_month)

# Invoice data
sent_invoices = [i for i in invoices if i["status"] in ("sent", "overdue")]
overdue_invoices = [i for i in invoices if i["status"] == "overdue"]
total_outstanding = sum(i["total_with_tax"] for i in sent_invoices)
total_overdue = sum(i["total_with_tax"] for i in overdue_invoices)

# ══════════════════════════════════════════════════════════════
# ROW 1: FINANCIAL HEALTH
# ══════════════════════════════════════════════════════════════

st.markdown("### Financieel")

c1, c2, c3, c4 = st.columns(4)
with c1:
    if bank_balance is not None:
        st.metric("Banksaldo", f"EUR {bank_balance:,.0f}")
    else:
        st.metric("Banksaldo", "—")
with c2:
    st.metric("Openstaand", f"EUR {total_outstanding:,.0f}")
with c3:
    if overdue_invoices:
        st.metric("Overdue", f"EUR {total_overdue:,.0f}",
                  delta=f"{len(overdue_invoices)} facturen", delta_color="inverse")
    else:
        st.metric("Overdue", "Geen", delta="Alles op tijd", delta_color="normal")
with c4:
    # Runway
    if bank_balance and monthly_cost > 0:
        available = bank_balance + total_outstanding
        bal = bank_balance
        outstanding_pool = total_outstanding
        months = 0
        for offset in range(24):
            m_idx = (current_month + offset) % 12
            plan_data = json.loads(COST_FILE.read_text(encoding="utf-8")) if COST_FILE.exists() else {"categories": {}, "one_offs": []}
            cost = sum(vals[m_idx] for vals in plan_data.get("categories", {}).values())
            cost += sum(oo["amount"] for oo in plan_data.get("one_offs", []) if oo["month"] == m_idx)
            income = outstanding_pool / 2 if offset < 2 and outstanding_pool > 0 else 0
            if offset < 2:
                outstanding_pool = max(0, outstanding_pool - income)
            bal = bal - cost + income
            if bal <= 0:
                break
            months += 1
        if months >= 12:
            st.metric("Runway", f"{months}+ mnd", delta="Gezond", delta_color="normal")
        elif months >= 6:
            st.metric("Runway", f"{months} mnd", delta="OK", delta_color="normal")
        elif months >= 3:
            st.metric("Runway", f"{months} mnd", delta="Aandacht", delta_color="off")
        else:
            st.metric("Runway", f"{months} mnd", delta="Kritiek", delta_color="inverse")
    else:
        st.metric("Runway", "—")

# ══════════════════════════════════════════════════════════════
# ROW 2: UREN VORIGE WEEK
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown(f"### Uren vorige week ({last_week_start.strftime('%d/%m')} — {last_week_end.strftime('%d/%m')})")

if time_last_week:
    te_df = pd.DataFrame(time_last_week)
    te_df["hours"] = te_df["minutes"] / 60
    te_df["person"] = te_df["person_id"].map(people_lookup).fillna("Onbekend")
    te_df["project"] = te_df["project_id"].map(project_lookup).fillna("Onbekend")

    total_hours = te_df["hours"].sum()
    billable_hours = te_df[te_df["billable"]]["hours"].sum()
    util_rate = (billable_hours / total_hours * 100) if total_hours > 0 else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Totaal", f"{total_hours:.0f}u")
    with c2:
        st.metric("Billable", f"{billable_hours:.0f}u")
    with c3:
        color = "inverse" if util_rate < 60 else "normal"
        st.metric("Billable %", f"{util_rate:.0f}%",
                  delta="Target: 70%" if util_rate < 70 else "Op target",
                  delta_color=color)

    # Per person compact
    person_df = te_df.groupby("person").agg(
        Totaal=("hours", "sum"),
        Billable=("hours", lambda x: x[te_df.loc[x.index, "billable"]].sum()),
    ).reset_index()

    cols = st.columns(len(person_df))
    for i, (_, row) in enumerate(person_df.iterrows()):
        with cols[i]:
            pct = (row["Billable"] / row["Totaal"] * 100) if row["Totaal"] > 0 else 0
            st.markdown(f"**{row['person']}**")
            st.markdown(f"{row['Totaal']:.0f}u ({row['Billable']:.0f}u billable, {pct:.0f}%)")
else:
    st.info("Geen uren geboekt vorige week.")

# ══════════════════════════════════════════════════════════════
# ROW 3: RESOURCING DEZE WEEK
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("### Resourcing deze week")

RESOURCING_FILE = Path(__file__).parent.parent / "data" / "resourcing.json"
week_num = today.isocalendar()[1]

if RESOURCING_FILE.exists():
    res_data = json.loads(RESOURCING_FILE.read_text(encoding="utf-8"))
    week_key = f"w{week_num}"
    if week_key in res_data:
        res_df = pd.DataFrame(res_data[week_key])
        alloc_cols = [c for c in res_df.columns if c not in ("Persoon", "Capaciteit")]
        if alloc_cols:
            res_df["Totaal"] = res_df[alloc_cols].sum(axis=1)
            res_df["Vrij"] = res_df["Capaciteit"] - res_df["Totaal"]

            for _, row in res_df.iterrows():
                free = row["Vrij"]
                alloc = row["Totaal"]
                cap = row["Capaciteit"]
                # Top projects
                top = [(c, row[c]) for c in alloc_cols if row[c] > 0]
                top.sort(key=lambda x: x[1], reverse=True)
                proj_str = ", ".join(f"{p} ({v:.1f}d)" for p, v in top[:3]) if top else "—"

                if free < 0:
                    status = ":red[Overbezet]"
                elif free < 0.5:
                    status = ":orange[Vol]"
                else:
                    status = f":green[{free:.1f}d vrij]"
                st.markdown(f"**{row['Persoon']}** ({alloc:.1f}/{cap:.1f}d) — {status} — {proj_str}")
        else:
            st.info("Resourcing nog niet ingevuld. Ga naar **Resourcing** om de week in te vullen.")
    else:
        st.info(f"Week {week_num} nog niet ingevuld. Ga naar **Resourcing**.")
else:
    st.info("Resourcing nog niet ingevuld. Ga naar **Resourcing** om de week in te vullen.")

# ══════════════════════════════════════════════════════════════
# ROW 4: PIPELINE HIGHLIGHTS
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("### Pipeline")

open_deals = [d for d in deals if not d.get("closed")]
if open_deals:
    deals_df = pd.DataFrame(open_deals)
    deals_df["company"] = deals_df["company_id"].map(company_lookup).fillna("")

    total_weighted = deals_df["weighted_value"].sum()
    n_deals = len(deals_df)

    # Top deals by weighted value
    top_deals = deals_df.nlargest(5, "weighted_value")

    c1, c2 = st.columns([1, 2])
    with c1:
        st.metric("Open deals", n_deals)
        st.metric("Gewogen waarde", f"EUR {total_weighted:,.0f}")
    with c2:
        for _, deal in top_deals.iterrows():
            company = deal["company"]
            name = deal["name"]
            prob = deal["probability"]
            rev = deal["revenue"]
            status = deal["status"]
            if rev > 0:
                st.markdown(f"**{company}** — {name} ({status}, {prob}%, EUR {rev:,.0f})")
            else:
                st.markdown(f"**{company}** — {name} ({status}, {prob}%)")
else:
    st.info("Geen open deals.")

# ══════════════════════════════════════════════════════════════
# ACTIONS / FLAGS
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("### Actiepunten")

flags = []
if overdue_invoices:
    for inv in overdue_invoices:
        flags.append(f"Factuur **{inv['number']}** is overdue (EUR {inv['total_with_tax']:,.0f})")
if bank_balance and monthly_cost > 0 and bank_balance < monthly_cost * 3:
    flags.append(f"Banksaldo (EUR {bank_balance:,.0f}) is minder dan 3 maanden kosten")
if time_last_week:
    te_df_check = pd.DataFrame(time_last_week)
    te_df_check["hours"] = te_df_check["minutes"] / 60
    if te_df_check["hours"].sum() < 20:
        flags.append(f"Vorige week maar {te_df_check['hours'].sum():.0f} uur geboekt — te weinig?")

if flags:
    for flag in flags:
        st.warning(flag)
else:
    st.success("Geen rode vlaggen. Goede week gehad!")
