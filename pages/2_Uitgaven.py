"""Uitgaven — Actual expenses from bank transactions."""
from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.bank_api import is_configured as bank_configured, get_transactions

st.markdown("# Uitgaven")
st.caption("Werkelijke uitgaven op basis van banktransacties.")

# ── Auto-categorization rules ──
CATEGORY_RULES = {
    "Salarissen": ["loonheffing", "salaris", "dga"],
    "Boekhouder": ["slingerland"],
    "Software & tools": ["anthropic", "claude", "github", "streamlit", "zapier", "plaud",
                         "docusign", "think-cell", "microsoft", "norton", "cloudflare"],
    "Kantoor": ["spaces", "swoh", "plnt", "huur"],
    "Verzekeringen": ["verzekering", "insurance", "anker"],
    "Reiskosten": ["ns.nl", "ov-chipkaart", "transvia", "parkeer", "shell", "bp "],
    "Telecom": ["odido", "kpn", "t-mobile"],
    "Belasting": ["belastingdienst", "gemeente", "kvk"],
    "Bank": ["transactiekosten", "rente"],
    "Inhuur": ["gerben", "vermeulen", "eddie"],
}


def _categorize(description: str) -> str:
    desc_lower = description.lower()
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return "Overig"


if not bank_configured():
    st.info("Koppel je bankrekening bij **Instellingen** om uitgaven automatisch te laden.")
    st.stop()

# ── Sidebar: period ──
with st.sidebar:
    st.markdown("### Periode")
    period = st.selectbox("Toon", ["Laatste 30 dagen", "Laatste 90 dagen", "Dit jaar"], key="exp_period")
    days_map = {"Laatste 30 dagen": 30, "Laatste 90 dagen": 90, "Dit jaar": (date.today() - date(2026, 1, 1)).days}
    days = days_map[period]

# ── Load transactions ──
with st.spinner("Transacties ophalen..."):
    transactions = get_transactions(days=days)

if not transactions:
    st.warning("Geen transacties gevonden voor deze periode.")
    st.stop()

df = pd.DataFrame(transactions)
outgoing = df[df["amount"] < 0].copy()
incoming = df[df["amount"] > 0].copy()

outgoing["amount"] = outgoing["amount"].abs()
outgoing["category"] = outgoing["description"].apply(_categorize)

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

total_out = outgoing["amount"].sum()
total_in = incoming["amount"].sum()
n_transactions = len(outgoing)

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Totaal uitgegeven", f"EUR {total_out:,.0f}")
with c2:
    st.metric("Totaal ontvangen", f"EUR {total_in:,.0f}")
with c3:
    netto = total_in - total_out
    st.metric("Netto", f"EUR {netto:,.0f}",
              delta="Positief" if netto > 0 else "Negatief",
              delta_color="normal" if netto > 0 else "inverse")

# ══════════════════════════════════════════════════════════════
# PER CATEGORIE
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Per Categorie")

cat_df = outgoing.groupby("category")["amount"].sum().sort_values(ascending=True).reset_index()
cat_df.columns = ["Categorie", "Bedrag"]

fig = go.Figure()
fig.add_trace(go.Bar(
    y=cat_df["Categorie"], x=cat_df["Bedrag"],
    orientation="h",
    marker_color="#003566",
    text=cat_df["Bedrag"].apply(lambda x: f"EUR {x:,.0f}"),
    textposition="outside",
))
fig.update_layout(
    height=max(200, len(cat_df) * 40),
    margin=dict(l=0, r=80, t=10, b=0),
    template="plotly_white",
)
st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# MAANDTREND
# ══════════════════════════════════════════════════════════════

if days >= 60:
    st.divider()
    st.markdown("#### Maandtrend")

    outgoing["month"] = pd.to_datetime(outgoing["date"]).dt.to_period("M").astype(str)
    monthly = outgoing.groupby("month")["amount"].sum().reset_index()
    monthly.columns = ["Maand", "Uitgaven"]

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(
        x=monthly["Maand"], y=monthly["Uitgaven"],
        marker_color="#003566",
        text=monthly["Uitgaven"].apply(lambda x: f"EUR {x:,.0f}"),
        textposition="outside",
    ))
    fig_trend.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="EUR", template="plotly_white",
    )
    st.plotly_chart(fig_trend, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# ALLE TRANSACTIES
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Alle Uitgaven")

display = outgoing[["date", "description", "amount", "category"]].copy()
display.columns = ["Datum", "Omschrijving", "Bedrag", "Categorie"]
display = display.sort_values("Datum", ascending=False)
display["Bedrag"] = display["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
st.dataframe(display, use_container_width=True, hide_index=True)

# ── Inkomsten ──
st.divider()
st.markdown("#### Inkomsten")
if not incoming.empty:
    inc_display = incoming[["date", "description", "amount"]].copy()
    inc_display.columns = ["Datum", "Omschrijving", "Bedrag"]
    inc_display = inc_display.sort_values("Datum", ascending=False)
    inc_display["Bedrag"] = inc_display["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
    st.dataframe(inc_display, use_container_width=True, hide_index=True)
else:
    st.info("Geen inkomsten in deze periode.")
