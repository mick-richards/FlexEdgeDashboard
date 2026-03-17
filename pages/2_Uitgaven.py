"""Uitgaven — Actual expenses from bank transactions with editable categories."""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.bank_api import is_configured as bank_configured, get_transactions

st.markdown("# Uitgaven")
st.caption("Werkelijke uitgaven op basis van banktransacties. Categorieën zijn aanpasbaar.")

# ── Category overrides persistence ──
OVERRIDES_FILE = Path(__file__).parent.parent / "data" / "category_overrides.json"
OVERRIDES_FILE.parent.mkdir(exist_ok=True)


def _load_overrides() -> dict:
    if OVERRIDES_FILE.exists():
        return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    return {}


def _save_overrides(overrides: dict) -> None:
    OVERRIDES_FILE.write_text(json.dumps(overrides, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Auto-categorization rules ──
ALL_CATEGORIES = [
    "Salarissen", "Boekhouder", "Software & tools", "Kantoor",
    "Verzekeringen", "Reiskosten", "Telecom", "Belasting", "Bank",
    "Inhuur", "Marketing & acquisitie", "Opleiding", "Overig",
]

CATEGORY_RULES = {
    "Salarissen": ["loonheffing", "salaris", "dga", "pensioen", "netto loon"],
    "Boekhouder": ["slingerland"],
    "Software & tools": ["anthropic", "claude", "github", "streamlit", "zapier", "plaud",
                         "docusign", "think-cell", "microsoft", "norton", "cloudflare",
                         "productive", "miro", "canva", "notion", "figma", "google", "adobe", "gamma"],
    "Kantoor": ["spaces", "swoh", "plnt", "huur"],
    "Verzekeringen": ["verzekering", "insurance", "anker"],
    "Reiskosten": ["ns.nl", "ov-chipkaart", "transvia", "parkeer", "shell", "bp ",
                   "uber", "taxi", "booking", "hotel", "benzine", "parkeren"],
    "Telecom": ["odido", "kpn", "t-mobile"],
    "Belasting": ["belastingdienst", "gemeente", "kvk", "btw", "vennootschapsbelasting"],
    "Bank": ["transactiekosten", "rente"],
    "Inhuur": ["gerben", "vermeulen", "eddie"],
    "Marketing & acquisitie": ["lunch", "restaurant", "eten", "event", "netwerk", "borrel"],
    "Opleiding": ["cursus", "course", "training", "boek", "conferentie"],
}


def _categorize(description: str) -> str:
    desc_lower = description.lower()
    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in desc_lower:
                return category
    return "Overig"


def _make_tx_key(row: dict) -> str:
    """Create a unique key for a transaction (date + amount + description truncated)."""
    return f"{row.get('date', '')}|{row.get('amount', '')}|{str(row.get('description', ''))[:50]}"


if not bank_configured():
    st.info("Koppel je bankrekening bij **Instellingen** om uitgaven automatisch te laden.")
    st.stop()

# ── Sidebar: period ──
with st.sidebar:
    st.markdown("### Periode")
    period = st.selectbox("Toon", ["Laatste 30 dagen", "Laatste 90 dagen", "Dit jaar"], key="exp_period")
    today = date.today()
    days_map = {"Laatste 30 dagen": 30, "Laatste 90 dagen": 90, "Dit jaar": (today - date(today.year, 1, 1)).days}
    days = days_map[period]

# ── Load transactions + overrides ──
with st.spinner("Transacties ophalen..."):
    transactions = get_transactions(days=days)

overrides = _load_overrides()

if not transactions:
    st.warning("Geen transacties gevonden voor deze periode.")
    st.stop()

df = pd.DataFrame(transactions)
outgoing = df[df["amount"] < 0].copy()
incoming = df[df["amount"] > 0].copy()

outgoing["amount"] = outgoing["amount"].abs()
outgoing["auto_category"] = outgoing["description"].apply(_categorize)
outgoing["tx_key"] = outgoing.apply(lambda r: _make_tx_key(r), axis=1)
outgoing["category"] = outgoing.apply(
    lambda r: overrides.get(r["tx_key"], r["auto_category"]), axis=1
)

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

total_out = outgoing["amount"].sum()
total_in = incoming["amount"].sum()

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
# ALLE TRANSACTIES (met bewerkbare categorie)
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Alle Uitgaven")
st.caption("Klik op een categorie om deze aan te passen. Wijzigingen worden automatisch onthouden.")

display = outgoing[["date", "description", "amount", "category", "tx_key"]].copy()
display = display.sort_values("date", ascending=False).reset_index(drop=True)

edited_df = st.data_editor(
    display[["date", "description", "amount", "category"]].rename(
        columns={"date": "Datum", "description": "Omschrijving", "amount": "Bedrag", "category": "Categorie"}
    ),
    use_container_width=True,
    hide_index=True,
    key="tx_editor",
    disabled=["Datum", "Omschrijving", "Bedrag"],
    column_config={
        "Categorie": st.column_config.SelectboxColumn(
            options=ALL_CATEGORIES,
            width="medium",
        ),
        "Bedrag": st.column_config.NumberColumn(format="EUR %.2f"),
    },
)

# Detect changes and save overrides
if edited_df is not None:
    changed = False
    for idx, row in edited_df.iterrows():
        tx_key = display.iloc[idx]["tx_key"]
        new_cat = row["Categorie"]
        auto_cat = outgoing[outgoing["tx_key"] == tx_key]["auto_category"].iloc[0] if tx_key in outgoing["tx_key"].values else None
        if new_cat != auto_cat:
            if overrides.get(tx_key) != new_cat:
                overrides[tx_key] = new_cat
                changed = True
        elif tx_key in overrides:
            del overrides[tx_key]
            changed = True
    if changed:
        _save_overrides(overrides)
        st.rerun()

if overrides:
    with st.sidebar:
        st.divider()
        st.markdown(f"### Aangepast")
        st.caption(f"{len(overrides)} transactie(s) handmatig gecategoriseerd")
        if st.button("Reset alle overschrijvingen"):
            _save_overrides({})
            st.rerun()

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
