"""Runway — Cash position, burn rate, and financial projection."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_invoices
from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Runway")
st.caption("Hoeveel maanden kunnen we door? Live banksaldo, kosten per maand, en projectie.")

# ── Cost plan data file ──
COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
COST_FILE.parent.mkdir(exist_ok=True)

MONTHS_2026 = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
MONTH_DATES = [date(2026, m, 1) for m in range(1, 13)]


def _load_cost_plan() -> dict:
    if COST_FILE.exists():
        return json.loads(COST_FILE.read_text(encoding="utf-8"))
    # Defaults based on FlexEdge situation
    return {
        "categories": {
            "DGA salaris Mick": [2500, 2500, 2500, 3625, 3625, 3625, 3625, 3625, 3625, 3625, 3625, 3625],
            "DGA salaris Joris": [0, 0, 0, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000, 2000],
            "Stagevergoeding Tessa": [500, 500, 500, 500, 500, 500, 0, 0, 0, 0, 0, 0],
            "Kantoor": [500, 500, 500, 800, 800, 800, 800, 800, 800, 800, 800, 800],
            "Software & tools": [300, 300, 300, 300, 300, 300, 300, 300, 300, 300, 300, 300],
            "Boekhouder": [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200],
            "Verzekeringen": [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200],
            "Reiskosten": [300, 300, 300, 300, 300, 300, 300, 300, 300, 300, 300, 300],
            "Overig": [200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200, 200],
        },
        "one_offs": [],  # {"month": 3, "description": "...", "amount": 1000}
    }


def _save_cost_plan(plan: dict) -> None:
    COST_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


cost_plan = _load_cost_plan()

# ── Data ──
today = date.today()
current_month_idx = today.month - 1  # 0-based
year_start = today.replace(month=1, day=1)

invoices = get_invoices()
sent_invoices = [i for i in invoices if i["status"] in ("sent", "overdue")]
overdue_invoices = [i for i in invoices if i["status"] == "overdue"]
paid_ytd = [i for i in invoices if i["status"] == "paid"
            and (i.get("paid_date") or "") >= year_start.isoformat()]

total_outstanding = sum(i["total_with_tax"] for i in sent_invoices)
total_overdue = sum(i["total_with_tax"] for i in overdue_invoices)
total_paid_ytd = sum(i["total_with_tax"] for i in paid_ytd)

# ── Bank balance ──
if bank_configured():
    balance_data = get_balance()
    bank_balance = balance_data["amount"] if balance_data else None
    balance_date = balance_data.get("date") or today.isoformat() if balance_data else None
    balance_source = "ASN Bank (live)"
else:
    bank_balance = None
    balance_date = None
    balance_source = None

# Sidebar manual override
with st.sidebar:
    if bank_balance is None:
        st.markdown("### Banksaldo (handmatig)")
        manual_balance = st.number_input("Saldo (EUR)", value=0, step=1000, key="manual_balance")
        if manual_balance > 0:
            bank_balance = float(manual_balance)
            balance_date = today.isoformat()
            balance_source = "Handmatig"
    else:
        st.success(f"Bank: EUR {bank_balance:,.2f}")

# ══════════════════════════════════════════════════════════════
# KPI ROW
# ══════════════════════════════════════════════════════════════

c1, c2, c3, c4 = st.columns(4)
with c1:
    if bank_balance is not None:
        st.metric("Banksaldo", f"EUR {bank_balance:,.0f}",
                  help=f"Per {balance_date} ({balance_source})")
    else:
        st.metric("Banksaldo", "Niet beschikbaar")
with c2:
    st.metric("Openstaand", f"EUR {total_outstanding:,.0f}")
with c3:
    st.metric("Overdue", f"EUR {total_overdue:,.0f}",
              delta=f"{len(overdue_invoices)} facturen" if overdue_invoices else "Geen",
              delta_color="inverse" if overdue_invoices else "normal")
with c4:
    st.metric("Betaald YTD", f"EUR {total_paid_ytd:,.0f}")

# ══════════════════════════════════════════════════════════════
# MONTHLY COST PLAN
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Kostenplan 2026")
st.caption("Pas de maandelijkse kosten aan — salarissen, kantoor, eenmalige uitgaven. Klik 'Opslaan' na wijzigingen.")

# Build editable dataframe
cost_data = {"Categorie": list(cost_plan["categories"].keys())}
for i, month_name in enumerate(MONTHS_2026):
    cost_data[month_name] = [vals[i] for vals in cost_plan["categories"].values()]

cost_df = pd.DataFrame(cost_data)

edited_costs = st.data_editor(
    cost_df,
    use_container_width=True,
    hide_index=True,
    key="cost_editor",
    column_config={
        "Categorie": st.column_config.TextColumn(disabled=True, width="medium"),
    },
)

# One-off costs
st.markdown("##### Eenmalige kosten")
with st.expander("Eenmalige kosten toevoegen/bekijken"):
    one_offs = cost_plan.get("one_offs", [])

    with st.form("add_one_off", clear_on_submit=True):
        oo_cols = st.columns([1, 2, 1])
        with oo_cols[0]:
            oo_month = st.selectbox("Maand", MONTHS_2026, index=current_month_idx)
        with oo_cols[1]:
            oo_desc = st.text_input("Omschrijving", placeholder="bijv. WBSO advieskosten")
        with oo_cols[2]:
            oo_amount = st.number_input("Bedrag (EUR)", min_value=0, step=100, key="oo_amt")
        if st.form_submit_button("Toevoegen"):
            if oo_desc and oo_amount > 0:
                one_offs.append({
                    "month": MONTHS_2026.index(oo_month),
                    "description": oo_desc,
                    "amount": oo_amount,
                })
                cost_plan["one_offs"] = one_offs
                _save_cost_plan(cost_plan)
                st.rerun()

    if one_offs:
        for i, oo in enumerate(one_offs):
            st.markdown(f"- **{MONTHS_2026[oo['month']]}**: {oo['description']} — EUR {oo['amount']:,.0f}")

# Save button
if st.button("Kostenplan opslaan", type="primary"):
    # Update categories from edited dataframe
    if edited_costs is not None:
        for _, row in edited_costs.iterrows():
            cat = row["Categorie"]
            cost_plan["categories"][cat] = [float(row[m]) for m in MONTHS_2026]
    _save_cost_plan(cost_plan)
    st.success("Kostenplan opgeslagen!")

# ══════════════════════════════════════════════════════════════
# CALCULATE MONTHLY TOTALS
# ══════════════════════════════════════════════════════════════

monthly_recurring = []
for m_idx in range(12):
    total = sum(vals[m_idx] for vals in cost_plan["categories"].values())
    # Add one-offs for this month
    for oo in cost_plan.get("one_offs", []):
        if oo["month"] == m_idx:
            total += oo["amount"]
    monthly_recurring.append(total)

# Current month costs
current_monthly = monthly_recurring[current_month_idx]

# ══════════════════════════════════════════════════════════════
# RUNWAY PROJECTION
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Runway Projectie")

if bank_balance is not None and bank_balance > 0:
    # Calculate runway using per-month costs
    available = bank_balance + total_outstanding

    c_r1, c_r2, c_r3 = st.columns(3)
    with c_r1:
        st.metric("Beschikbaar", f"EUR {available:,.0f}",
                  help="Banksaldo + openstaande facturen")
    with c_r2:
        st.metric("Kosten deze maand", f"EUR {current_monthly:,.0f}")
    with c_r3:
        # Calculate months until zero using actual cost plan
        bal = bank_balance
        months_remaining = 0
        for future_month in range(current_month_idx, 24):  # Look 2 years ahead
            m_idx = future_month % 12
            cost = monthly_recurring[m_idx]
            # Add outstanding income spread over 2 months
            if future_month < current_month_idx + 2:
                bal += total_outstanding / 2
                total_outstanding_copy = 0  # only count once
            bal -= cost
            if bal <= 0:
                break
            months_remaining += 1

        if months_remaining >= 12:
            delta_text, delta_color = "Gezond", "normal"
        elif months_remaining >= 6:
            delta_text, delta_color = "OK", "normal"
        elif months_remaining >= 3:
            delta_text, delta_color = "Aandacht", "off"
        else:
            delta_text, delta_color = "Kritiek", "inverse"
        st.metric("Runway", f"{months_remaining} maanden",
                  delta=delta_text, delta_color=delta_color)

    # Projection chart with actual monthly costs
    proj_dates = []
    proj_balances = []
    proj_costs = []
    bal = bank_balance
    outstanding_remaining = total_outstanding

    for m_offset in range(13):  # 12 months ahead
        future_month_idx = (current_month_idx + m_offset) % 12
        d = date(2026 + (current_month_idx + m_offset) // 12, future_month_idx + 1, 1)
        proj_dates.append(d)
        proj_balances.append(bal)

        cost = monthly_recurring[future_month_idx]
        proj_costs.append(cost)

        # Assume outstanding collected in first 2 months
        income = outstanding_remaining / 2 if m_offset < 2 and outstanding_remaining > 0 else 0
        if m_offset < 2:
            outstanding_remaining -= income
        bal = bal - cost + income

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=proj_dates, y=proj_balances,
        mode="lines+markers",
        line=dict(color="#003566", width=2.5),
        marker=dict(size=7),
        name="Saldo",
    ))
    fig.add_trace(go.Bar(
        x=proj_dates, y=proj_costs,
        marker_color="rgba(230, 57, 70, 0.3)",
        name="Maandkosten",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#E63946", annotation_text="Zero")
    fig.update_layout(
        height=380, margin=dict(l=0, r=0, t=30, b=0),
        yaxis_title="EUR", template="plotly_white",
        legend=dict(orientation="h", y=1.1),
        barmode="overlay",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Cost breakdown table
    st.markdown("#### Kosten per Maand")
    summary_data = {
        "Maand": [MONTHS_2026[i] for i in range(current_month_idx, 12)],
        "Terugkerend": [sum(vals[i] for vals in cost_plan["categories"].values()) for i in range(current_month_idx, 12)],
        "Eenmalig": [
            sum(oo["amount"] for oo in cost_plan.get("one_offs", []) if oo["month"] == i)
            for i in range(current_month_idx, 12)
        ],
    }
    summary_data["Totaal"] = [r + e for r, e in zip(summary_data["Terugkerend"], summary_data["Eenmalig"])]
    summary_df = pd.DataFrame(summary_data)
    summary_df["Terugkerend"] = summary_df["Terugkerend"].apply(lambda x: f"EUR {x:,.0f}")
    summary_df["Eenmalig"] = summary_df["Eenmalig"].apply(lambda x: f"EUR {x:,.0f}" if x > 0 else "-")
    summary_df["Totaal"] = summary_df["Totaal"].apply(lambda x: f"EUR {x:,.0f}")
    st.dataframe(summary_df, use_container_width=True, hide_index=True)

else:
    st.info("Banksaldo niet beschikbaar — controleer de bankkoppeling bij Instellingen.")

# ══════════════════════════════════════════════════════════════
# OPEN INVOICES
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Openstaande Facturen")
if sent_invoices:
    df = pd.DataFrame(sent_invoices)[["number", "date", "due_date", "total_with_tax", "status"]]
    df.columns = ["Nummer", "Datum", "Vervaldatum", "Bedrag", "Status"]
    df["Bedrag"] = df["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.success("Geen openstaande facturen.")
