"""Runway — Cash position and burn rate overview."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_invoices
from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Runway")
st.caption("Hoeveel maanden kunnen we door op basis van huidig saldo en verwachte inkomsten?")

# ── Sidebar: fixed costs + manual balance ──
with st.sidebar:
    st.markdown("### Banksaldo")
    manual_balance = st.number_input(
        "Huidig saldo (EUR)", value=0, step=1000, key="manual_balance",
        help="Vul je huidige banksaldo in. Wordt automatisch als de bankkoppeling actief is.",
    )
    balance_date_input = st.date_input("Peildatum", value=date.today(), key="balance_date")

    st.divider()
    st.markdown("### Vaste Lasten / maand")
    monthly_salary = st.number_input("Salarissen", value=8500, step=500, key="s_salary")
    monthly_office = st.number_input("Kantoor & tools", value=1500, step=100, key="s_office")
    monthly_other = st.number_input("Overig", value=500, step=100, key="s_other")
    total_fixed = monthly_salary + monthly_office + monthly_other
    st.metric("Totaal", f"EUR {total_fixed:,.0f}")

# ── Data ──
today = date.today()
year_start = today.replace(month=1, day=1)

invoices = get_invoices()
sent_invoices = [i for i in invoices if i["status"] in ("sent", "overdue")]
overdue_invoices = [i for i in invoices if i["status"] == "overdue"]
paid_ytd = [i for i in invoices if i["status"] == "paid"
            and (i.get("paid_date") or "") >= year_start.isoformat()]

total_outstanding = sum(i["total_with_tax"] for i in sent_invoices)
total_overdue = sum(i["total_with_tax"] for i in overdue_invoices)
total_paid_ytd = sum(i["total_with_tax"] for i in paid_ytd)

# ── Bank balance: prefer API, fallback to manual ──
if bank_configured():
    balance_data = get_balance()
    bank_balance = balance_data["amount"] if balance_data else None
    balance_date = balance_data["date"] if balance_data else None
    balance_source = "GoCardless"
else:
    bank_balance = None
    balance_date = None
    balance_source = None

# Use manual balance if no API
if bank_balance is None and manual_balance > 0:
    bank_balance = float(manual_balance)
    balance_date = balance_date_input.isoformat()
    balance_source = "Handmatig"

# ── KPI row ──
c1, c2, c3, c4 = st.columns(4)
with c1:
    if bank_balance is not None:
        st.metric("Banksaldo", f"EUR {bank_balance:,.0f}",
                  help=f"Per {balance_date} ({balance_source})")
    else:
        st.metric("Banksaldo", "Vul in via sidebar")
with c2:
    st.metric("Openstaand", f"EUR {total_outstanding:,.0f}")
with c3:
    st.metric("Overdue", f"EUR {total_overdue:,.0f}",
              delta=f"{len(overdue_invoices)} facturen", delta_color="inverse")
with c4:
    st.metric("Betaald YTD", f"EUR {total_paid_ytd:,.0f}")

st.divider()

# ── Runway calculation ──
if bank_balance is not None and bank_balance > 0:
    available = bank_balance + total_outstanding
    runway_months = available / total_fixed if total_fixed > 0 else 99

    c_r1, c_r2, c_r3 = st.columns(3)
    with c_r1:
        st.metric("Beschikbaar", f"EUR {available:,.0f}",
                  help="Saldo + openstaande facturen")
    with c_r2:
        st.metric("Maandkosten", f"EUR {total_fixed:,.0f}")
    with c_r3:
        if runway_months >= 6:
            delta_text, delta_color = "Gezond", "normal"
        elif runway_months >= 3:
            delta_text, delta_color = "Aandacht", "off"
        else:
            delta_text, delta_color = "Kritiek", "inverse"
        st.metric("Runway", f"{runway_months:.1f} maanden",
                  delta=delta_text, delta_color=delta_color)

    # Projection chart
    months_ahead = 6
    dates, balances = [], []
    bal = bank_balance
    for m in range(months_ahead + 1):
        d = today.replace(day=1) + timedelta(days=32 * m)
        d = d.replace(day=1)
        dates.append(d)
        balances.append(bal)
        income = total_outstanding / 3 if m < 3 else 0
        bal = bal - total_fixed + income

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=balances,
        mode="lines+markers",
        line=dict(color="#003566", width=2),
        marker=dict(size=6),
        name="Saldo projectie",
    ))
    fig.add_hline(y=0, line_dash="dash", line_color="#E63946", annotation_text="Zero")
    fig.add_hline(y=total_fixed * 3, line_dash="dot", line_color="#F4A261",
                  annotation_text="3 mnd reserve")
    fig.update_layout(
        height=320, margin=dict(l=0, r=0, t=30, b=0),
        yaxis_title="EUR", template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Vul je banksaldo in via de sidebar om de runway te berekenen.")

# ── Open invoices table ──
st.divider()
st.markdown("#### Openstaande Facturen")
if sent_invoices:
    df = pd.DataFrame(sent_invoices)[["number", "date", "due_date", "total_with_tax", "status"]]
    df.columns = ["Nummer", "Datum", "Vervaldatum", "Bedrag", "Status"]
    df["Bedrag"] = df["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.success("Geen openstaande facturen.")
