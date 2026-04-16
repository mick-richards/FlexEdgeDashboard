"""Runway — Financial overview combining bank balance, invoices, and cost plan."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_invoices, safe_load
from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Runway")
st.caption("Banksaldo, verwachte inkomsten en kosten — hoelang kunnen we door?")

# ── Load cost plan ──
COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
MONTHS = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]


def _load_cost_plan() -> dict:
    if COST_FILE.exists():
        return json.loads(COST_FILE.read_text(encoding="utf-8"))
    return {"categories": {}, "one_offs": []}


cost_plan = _load_cost_plan()

# Monthly costs from plan
monthly_costs = []
for m_idx in range(12):
    recurring = sum(vals[m_idx] for vals in cost_plan.get("categories", {}).values())
    oneoff = sum(oo["amount"] for oo in cost_plan.get("one_offs", []) if oo["month"] == m_idx)
    monthly_costs.append(recurring + oneoff)

# ── Data ──
today = date.today()
current_month = today.month - 1
year_start = today.replace(month=1, day=1)

invoices = safe_load(get_invoices)
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
else:
    bank_balance = None
    balance_date = None

# Sidebar manual fallback
with st.sidebar:
    if bank_balance is not None:
        st.success(f"ASN Bank: EUR {bank_balance:,.2f}")
    else:
        st.markdown("### Banksaldo")
        manual = st.number_input("Saldo (EUR)", value=0, step=1000, key="manual_bal")
        if manual > 0:
            bank_balance = float(manual)
            balance_date = today.isoformat()

    if monthly_costs and any(c > 0 for c in monthly_costs):
        st.divider()
        st.markdown(f"**Kosten deze maand:** EUR {monthly_costs[current_month]:,.0f}")
        avg_remaining = sum(monthly_costs[current_month:]) / max(12 - current_month, 1)
        st.markdown(f"**Gem. komende mnd:** EUR {avg_remaining:,.0f}")
    else:
        st.warning("Geen kostenplan. Ga naar **Kostenplan** om kosten in te vullen.")

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

c1, c2, c3, c4 = st.columns(4)
with c1:
    if bank_balance is not None:
        st.metric("Banksaldo", f"EUR {bank_balance:,.0f}",
                  help=f"Per {balance_date}")
    else:
        st.metric("Banksaldo", "Niet beschikbaar")
with c2:
    st.metric("Openstaand", f"EUR {total_outstanding:,.0f}")
with c3:
    st.metric("Overdue", f"EUR {total_overdue:,.0f}",
              delta=f"{len(overdue_invoices)} facturen" if overdue_invoices else "Geen",
              delta_color="inverse" if overdue_invoices else "normal")
with c4:
    st.metric("Omzet YTD", f"EUR {total_paid_ytd:,.0f}")

# ══════════════════════════════════════════════════════════════
# RUNWAY
# ══════════════════════════════════════════════════════════════

st.divider()

if bank_balance is not None and bank_balance > 0 and any(c > 0 for c in monthly_costs):
    # Calculate runway with real monthly costs
    bal = bank_balance
    outstanding_pool = total_outstanding
    months_remaining = 0

    for offset in range(24):
        m_idx = (current_month + offset) % 12
        cost = monthly_costs[m_idx]
        # Assume outstanding collected over first 2 months
        income = outstanding_pool / 2 if offset < 2 and outstanding_pool > 0 else 0
        if offset < 2:
            outstanding_pool = max(0, outstanding_pool - income)
        bal = bal - cost + income
        if bal <= 0:
            break
        months_remaining += 1

    available = bank_balance + total_outstanding

    c_r1, c_r2, c_r3 = st.columns(3)
    with c_r1:
        st.metric("Beschikbaar", f"EUR {available:,.0f}",
                  help="Banksaldo + openstaande facturen")
    with c_r2:
        st.metric("Kosten deze maand", f"EUR {monthly_costs[current_month]:,.0f}")
    with c_r3:
        if months_remaining >= 12:
            label, color = "Gezond", "normal"
        elif months_remaining >= 6:
            label, color = "OK", "normal"
        elif months_remaining >= 3:
            label, color = "Aandacht", "off"
        else:
            label, color = "Kritiek", "inverse"
        st.metric("Runway", f"{months_remaining} maanden", delta=label, delta_color=color)

    # ── Projection chart ──
    st.markdown("#### 12-maanden projectie")

    proj_dates = []
    proj_bal = []
    proj_cost = []
    proj_income = []
    bal = bank_balance
    outstanding_pool = total_outstanding

    for offset in range(13):
        m_idx = (current_month + offset) % 12
        year = today.year + (current_month + offset) // 12
        d = date(year, m_idx + 1, 1)
        proj_dates.append(d)
        proj_bal.append(bal)

        cost = monthly_costs[m_idx]
        income = outstanding_pool / 2 if offset < 2 and outstanding_pool > 0 else 0
        if offset < 2:
            outstanding_pool = max(0, outstanding_pool - income)

        proj_cost.append(cost)
        proj_income.append(income)
        bal = bal - cost + income

    fig = go.Figure()

    # Balance line
    fig.add_trace(go.Scatter(
        x=proj_dates, y=proj_bal,
        mode="lines+markers",
        line=dict(color="#003566", width=2.5),
        marker=dict(size=7),
        name="Saldo",
        hovertemplate="EUR %{y:,.0f}<extra>Saldo</extra>",
    ))

    # Cost bars
    fig.add_trace(go.Bar(
        x=proj_dates, y=proj_cost,
        marker_color="rgba(230, 57, 70, 0.3)",
        name="Kosten",
        hovertemplate="EUR %{y:,.0f}<extra>Kosten</extra>",
    ))

    # Income bars
    if any(v > 0 for v in proj_income):
        fig.add_trace(go.Bar(
            x=proj_dates, y=proj_income,
            marker_color="rgba(42, 157, 143, 0.4)",
            name="Verwachte inkomsten",
            hovertemplate="EUR %{y:,.0f}<extra>Inkomsten</extra>",
        ))

    fig.add_hline(y=0, line_dash="dash", line_color="#E63946")
    fig.update_layout(
        height=400, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="EUR", template="plotly_white",
        barmode="group",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, use_container_width=True)

elif bank_balance is None:
    st.info("Banksaldo niet beschikbaar — controleer de bankkoppeling bij **Instellingen**.")
else:
    st.warning("Vul het **Kostenplan** in om de runway te berekenen.")

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
