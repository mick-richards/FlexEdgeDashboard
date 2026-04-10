"""Weekstart — One-screen overview for the Monday check-in with Joris."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd

from services.productive_api import (
    get_invoices, get_time_entries, get_deals, get_people, get_projects,
    get_companies, build_lookup, safe_load,
)
from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Weekstart")
st.caption("Alles wat je nodig hebt voor de maandag check-in — in een scherm.")

today = date.today()
current_month = today.month - 1
last_week_start = today - timedelta(days=today.weekday() + 7)
last_week_end = last_week_start + timedelta(days=6)
week_num = today.isocalendar()[1]

# ── Load all data ──
with st.spinner("Data ophalen..."):
    invoices = safe_load(get_invoices)
    people = safe_load(get_people)
    projects = safe_load(get_projects)
    companies = safe_load(get_companies)
    deals = safe_load(get_deals)
    time_last_week = safe_load(get_time_entries,
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

# Cost plan — load once
COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
monthly_cost = 0
cost_plan = {"categories": {}, "one_offs": []}
if COST_FILE.exists():
    cost_plan = json.loads(COST_FILE.read_text(encoding="utf-8"))
    monthly_cost = sum(vals[current_month] for vals in cost_plan.get("categories", {}).values())
    monthly_cost += sum(oo["amount"] for oo in cost_plan.get("one_offs", []) if oo["month"] == current_month)

# Invoice data
sent_invoices = [i for i in invoices if i["status"] in ("sent", "overdue")]
overdue_invoices = [i for i in invoices if i["status"] == "overdue"]
total_outstanding = sum(i["total_with_tax"] for i in sent_invoices)
total_overdue = sum(i["total_with_tax"] for i in overdue_invoices)

# Pre-compute hours data
te_total_hours = 0
te_billable_hours = 0
te_df = None
if time_last_week:
    te_df = pd.DataFrame(time_last_week)
    te_df["hours"] = te_df["minutes"] / 60
    te_df["person"] = te_df["person_id"].map(people_lookup).fillna("Onbekend")
    te_df["project"] = te_df["project_id"].map(project_lookup).fillna("Onbekend")
    te_total_hours = te_df["hours"].sum()
    te_billable_hours = te_df[te_df["billable"]]["hours"].sum()

# Pre-compute runway (single pass, no re-reading file)
runway_months = None
if bank_balance and monthly_cost > 0:
    bal = bank_balance
    outstanding_pool = total_outstanding
    runway_months = 0
    for offset in range(24):
        m_idx = (current_month + offset) % 12
        cost = sum(vals[m_idx] for vals in cost_plan.get("categories", {}).values())
        cost += sum(oo["amount"] for oo in cost_plan.get("one_offs", []) if oo["month"] == m_idx)
        income = outstanding_pool / 2 if offset < 2 and outstanding_pool > 0 else 0
        if offset < 2:
            outstanding_pool = max(0, outstanding_pool - income)
        bal = bal - cost + income
        if bal <= 0:
            break
        runway_months += 1

# ══════════════════════════════════════════════════════════════
# FLAGS / ALERTS — at the top for instant visibility
# ══════════════════════════════════════════════════════════════

flags = []
if overdue_invoices:
    for inv in overdue_invoices:
        flags.append(f"Factuur **{inv['number']}** is overdue (EUR {inv['total_with_tax']:,.0f})")
if bank_balance and monthly_cost > 0 and bank_balance < monthly_cost * 3:
    flags.append(f"Banksaldo (EUR {bank_balance:,.0f}) is minder dan 3 maanden kosten")
if te_total_hours > 0 and te_total_hours < 20:
    flags.append(f"Vorige week maar {te_total_hours:.0f} uur geboekt — te weinig?")

if flags:
    for flag in flags:
        st.warning(flag, icon=":material/warning:")
else:
    st.success("Geen rode vlaggen. Goede week gehad!", icon=":material/check_circle:")

# ══════════════════════════════════════════════════════════════
# ROW 1: FINANCIAL KPIs — 4 compact metrics
# ══════════════════════════════════════════════════════════════

st.markdown("#### Financieel")

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
# ROW 2: Two columns — Uren (left) + Resourcing (right)
# ══════════════════════════════════════════════════════════════

col_left, col_right = st.columns(2, gap="large")

# ── Left: Uren vorige week ──
with col_left:
    st.markdown(f"#### Uren vorige week")
    st.caption(f"{last_week_start.strftime('%d/%m')} — {last_week_end.strftime('%d/%m')}")

    if te_df is not None and te_total_hours > 0:
        util_rate = (te_billable_hours / te_total_hours * 100) if te_total_hours > 0 else 0

        # Summary metrics in a row
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Totaal", f"{te_total_hours:.0f}u")
        with m2:
            st.metric("Billable", f"{te_billable_hours:.0f}u")
        with m3:
            color = "inverse" if util_rate < 60 else "normal"
            st.metric("Billable %", f"{util_rate:.0f}%",
                      delta="Target: 70%" if util_rate < 70 else "Op target",
                      delta_color=color)

        # Per person — compact metric cards
        person_df = te_df.groupby("person").agg(
            Totaal=("hours", "sum"),
            Billable=("hours", lambda x: x[te_df.loc[x.index, "billable"]].sum()),
        ).reset_index()
        person_df["Pct"] = (person_df["Billable"] / person_df["Totaal"] * 100).fillna(0)

        person_cols = st.columns(min(len(person_df), 4))
        for i, (_, row) in enumerate(person_df.iterrows()):
            with person_cols[i % len(person_cols)]:
                pct = row["Pct"]
                clr = "inverse" if pct < 50 else "off" if pct < 70 else "normal"
                st.metric(
                    row["person"],
                    f"{row['Totaal']:.0f}u",
                    delta=f"{row['Billable']:.0f}u billable ({pct:.0f}%)",
                    delta_color=clr,
                )
    else:
        st.info("Geen uren geboekt vorige week.")

# ── Right: Resourcing deze week ──
with col_right:
    st.markdown("#### Resourcing deze week")
    st.caption(f"Week {week_num}")

    RESOURCING_FILE = Path(__file__).parent.parent / "data" / "resourcing.json"

    if RESOURCING_FILE.exists():
        res_data = json.loads(RESOURCING_FILE.read_text(encoding="utf-8"))
        week_key = f"{week_num}"
        # Try both "w12" and "12" key formats
        if week_key not in res_data:
            week_key = f"w{week_num}"
        if week_key in res_data:
            res_df = pd.DataFrame(res_data[week_key])
            alloc_cols = [c for c in res_df.columns if c not in ("Persoon", "Capaciteit")]
            if alloc_cols:
                res_df["Totaal"] = res_df[alloc_cols].sum(axis=1)
                res_df["Vrij"] = res_df["Capaciteit"] - res_df["Totaal"]

                # Build a clean summary table
                summary_rows = []
                for _, row in res_df.iterrows():
                    free = row["Vrij"]
                    top = [(c, row[c]) for c in alloc_cols if row[c] > 0]
                    top.sort(key=lambda x: x[1], reverse=True)
                    proj_str = ", ".join(f"{p} ({v:.1f}d)" for p, v in top[:3]) if top else "—"

                    if free < 0:
                        status = "Overbezet"
                    elif free < 0.5:
                        status = "Vol"
                    else:
                        status = f"{free:.1f}d vrij"

                    summary_rows.append({
                        "Persoon": row["Persoon"],
                        "Bezetting": f"{row['Totaal']:.1f}/{row['Capaciteit']:.1f}d",
                        "Status": status,
                        "Projecten": proj_str,
                    })

                st.dataframe(
                    pd.DataFrame(summary_rows),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("Resourcing nog niet ingevuld.")
        else:
            st.info(f"Week {today.isocalendar()[1]} nog niet ingevuld. Ga naar **Resourcing**.")
    else:
        st.info("Resourcing nog niet ingevuld. Ga naar **Resourcing**.")

# ══════════════════════════════════════════════════════════════
# ROW 3: PIPELINE — compact top 5 table
# ══════════════════════════════════════════════════════════════

st.markdown("#### Pipeline")

open_deals = [d for d in deals if not d.get("closed")]
if open_deals:
    deals_df = pd.DataFrame(open_deals)
    deals_df["company"] = deals_df["company_id"].map(company_lookup).fillna("")

    total_weighted = deals_df["weighted_value"].sum()
    n_deals = len(deals_df)

    p1, p2 = st.columns([1, 3])
    with p1:
        st.metric("Open deals", n_deals)
        st.metric("Gewogen waarde", f"EUR {total_weighted:,.0f}")
    with p2:
        top_deals = deals_df.nlargest(5, "weighted_value")[
            ["company", "name", "status", "probability", "revenue", "weighted_value"]
        ].copy()
        top_deals.columns = ["Bedrijf", "Deal", "Stage", "Prob %", "Revenue", "Gewogen"]
        top_deals["Revenue"] = top_deals["Revenue"].apply(lambda x: f"EUR {x:,.0f}" if x > 0 else "—")
        top_deals["Gewogen"] = top_deals["Gewogen"].apply(lambda x: f"EUR {x:,.0f}" if x > 0 else "—")
        st.dataframe(top_deals, use_container_width=True, hide_index=True)
else:
    st.info("Geen open deals.")
