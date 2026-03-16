"""Uitgaven — Expense tracking and transaction log."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.bank_api import is_configured as bank_configured, get_transactions

st.markdown("# Uitgaven")
st.caption("Overzicht van alle uitgaven. Handmatig of automatisch via bankkoppeling.")

DATA_FILE = Path(__file__).parent.parent / "data" / "expenses.json"
DATA_FILE.parent.mkdir(exist_ok=True)

CATEGORIES = [
    "Salarissen",
    "Kantoor",
    "Software & tools",
    "Reiskosten",
    "Marketing",
    "Advies & accountant",
    "Verzekeringen",
    "Belastingen",
    "Inhuur / freelancers",
    "Overig",
]


def _load_expenses() -> list[dict]:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return []


def _save_expenses(expenses: list[dict]) -> None:
    DATA_FILE.write_text(json.dumps(expenses, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Load data ──
expenses = _load_expenses()

# ── Bank transactions (if connected) ──
if bank_configured():
    st.success("Bankkoppeling actief — transacties worden automatisch opgehaald.")
    bank_txns = get_transactions(days=90)
    if bank_txns:
        st.markdown("#### Banktransacties (laatste 90 dagen)")
        txn_df = pd.DataFrame(bank_txns)
        # Only show outgoing (negative amounts)
        outgoing = txn_df[txn_df["amount"] < 0].copy()
        outgoing["amount"] = outgoing["amount"].abs()
        if not outgoing.empty:
            outgoing = outgoing[["date", "description", "amount"]].copy()
            outgoing.columns = ["Datum", "Omschrijving", "Bedrag"]
            outgoing["Bedrag"] = outgoing["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
            st.dataframe(outgoing.head(50), use_container_width=True, hide_index=True)
        st.divider()

# ── Manual expense entry ──
st.markdown("#### Uitgave Toevoegen")

with st.form("add_expense", clear_on_submit=True):
    col1, col2, col3 = st.columns([1.5, 1, 1])
    with col1:
        desc = st.text_input("Omschrijving", placeholder="bijv. Claude Pro abonnement")
    with col2:
        amount = st.number_input("Bedrag (EUR)", min_value=0.0, step=10.0, format="%.2f")
    with col3:
        category = st.selectbox("Categorie", CATEGORIES)

    col4, col5 = st.columns(2)
    with col4:
        exp_date = st.date_input("Datum", value=date.today())
    with col5:
        recurring = st.selectbox("Frequentie", ["Eenmalig", "Maandelijks", "Jaarlijks"])

    submitted = st.form_submit_button("Toevoegen", type="primary", use_container_width=True)
    if submitted and desc and amount > 0:
        new_expense = {
            "date": exp_date.isoformat(),
            "description": desc,
            "amount": amount,
            "category": category,
            "recurring": recurring,
            "added": date.today().isoformat(),
        }
        expenses.append(new_expense)
        _save_expenses(expenses)
        st.success(f"Toegevoegd: {desc} — EUR {amount:,.2f}")
        st.rerun()

# ── Expense overview ──
if expenses:
    st.divider()
    df = pd.DataFrame(expenses)
    df["amount"] = df["amount"].astype(float)

    # Summary metrics
    total_expenses = df["amount"].sum()
    monthly_recurring = df[df["recurring"] == "Maandelijks"]["amount"].sum()
    yearly_recurring = df[df["recurring"] == "Jaarlijks"]["amount"].sum()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Totaal gelogd", f"EUR {total_expenses:,.0f}")
    with c2:
        st.metric("Maandelijks terugkerend", f"EUR {monthly_recurring:,.0f}")
    with c3:
        annual_burn = monthly_recurring * 12 + yearly_recurring
        st.metric("Jaarlijkse vaste kosten", f"EUR {annual_burn:,.0f}")

    # By category chart
    st.markdown("#### Per Categorie")
    cat_df = df.groupby("category")["amount"].sum().sort_values(ascending=True).reset_index()
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
        height=max(200, len(cat_df) * 35),
        margin=dict(l=0, r=80, t=10, b=0),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Full list
    st.markdown("#### Alle Uitgaven")
    display_df = df[["date", "description", "amount", "category", "recurring"]].copy()
    display_df.columns = ["Datum", "Omschrijving", "Bedrag", "Categorie", "Frequentie"]
    display_df = display_df.sort_values("Datum", ascending=False)
    display_df["Bedrag"] = display_df["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    # Delete option
    with st.expander("Uitgave verwijderen"):
        if expenses:
            options = [f"{e['date']} — {e['description']} (EUR {e['amount']:,.2f})" for e in expenses]
            to_delete = st.selectbox("Selecteer uitgave", options)
            if st.button("Verwijderen", type="secondary"):
                idx = options.index(to_delete)
                expenses.pop(idx)
                _save_expenses(expenses)
                st.success("Verwijderd")
                st.rerun()
else:
    st.info("Nog geen uitgaven gelogd. Voeg je eerste uitgave toe hierboven.")
