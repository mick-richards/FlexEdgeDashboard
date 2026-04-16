"""Mijn Holding — Privé holding-uitgaven registreren en zakelijke reiskosten doorboeken."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.emissions import TRAVEL_MODES, FACTORS
from services.bank_api import (
    is_configured as bank_configured, start_authorization, complete_authorization,
    get_balance_for_account, get_transactions_for_account,
    _load_holding_bank_config, save_holding_bank_config,
)

# ── Access control ──
user = st.session_state.get("user", "")
holding_name = st.session_state.get("user_holding", "")
if not user or not holding_name:
    st.warning("Log in met je persoonlijke account om je holding-uitgaven te zien.")
    st.stop()

st.markdown(f"# {holding_name}")
st.caption("Registreer holding-uitgaven. Markeer zakelijke reiskosten voor FlexEdge BV-emissies.")

# ── Data persistence ──
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
HOLDING_FILE = DATA_DIR / f"holding_{user}.json"

HOLDING_CATEGORIES = [
    "Reiskosten zakelijk",
    "Reiskosten privé",
    "Auto",
    "Telefoon",
    "Kantoorartikelen",
    "Representatie",
    "Overig",
]


def _load() -> list[dict]:
    if HOLDING_FILE.exists():
        data = json.loads(HOLDING_FILE.read_text(encoding="utf-8"))
        return data.get("transactions", [])
    return []


def _save(transactions: list[dict]) -> None:
    HOLDING_FILE.write_text(
        json.dumps({"transactions": transactions}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


transactions = _load()

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

today = date.today()
year_start = f"{today.year}-01-01"
ytd_txs = [t for t in transactions if t.get("date", "") >= year_start]
total_ytd = sum(t.get("amount", 0) for t in ytd_txs)
zakelijk_ytd = sum(t.get("amount", 0) for t in ytd_txs if t.get("zakelijk_flexedge"))
travel_ytd = sum(t.get("amount", 0) for t in ytd_txs if t.get("category") == "Reiskosten zakelijk")

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("Uitgaven YTD", f"EUR {total_ytd:,.0f}")
with c2:
    st.metric("Zakelijk FlexEdge", f"EUR {zakelijk_ytd:,.0f}")
with c3:
    st.metric("Reiskosten zakelijk", f"EUR {travel_ytd:,.0f}")

# ══════════════════════════════════════════════════════════════
# NIEUWE UITGAVE INVOEREN
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Nieuwe uitgave")

with st.form("new_holding_expense", clear_on_submit=True):
    fc1, fc2, fc3 = st.columns([1, 1, 1])
    with fc1:
        tx_date = st.date_input("Datum", value=today, key="h_date")
    with fc2:
        tx_amount = st.number_input("Bedrag (EUR)", min_value=0.0, step=10.0, key="h_amount")
    with fc3:
        tx_category = st.selectbox("Categorie", HOLDING_CATEGORIES, key="h_cat")

    fc4, fc5 = st.columns([2, 1])
    with fc4:
        tx_desc = st.text_input("Omschrijving", key="h_desc")
    with fc5:
        tx_zakelijk = st.checkbox("Zakelijk voor FlexEdge BV", key="h_zakelijk",
                                  value=(tx_category == "Reiskosten zakelijk") if "h_cat" in st.session_state else False)

    # Travel details (shown for reiskosten)
    show_travel = tx_category in ("Reiskosten zakelijk", "Reiskosten privé", "Auto")
    if show_travel:
        tc1, tc2 = st.columns(2)
        with tc1:
            tx_km = st.number_input("Afstand (km)", min_value=0, step=10, key="h_km")
        with tc2:
            tx_mode = st.selectbox("Vervoermiddel", list(TRAVEL_MODES.keys()), key="h_mode")
    else:
        tx_km = 0
        tx_mode = ""

    submitted = st.form_submit_button("Toevoegen", type="primary", use_container_width=True)
    if submitted and tx_amount > 0:
        new_tx = {
            "date": tx_date.isoformat(),
            "amount": float(tx_amount),
            "description": tx_desc,
            "category": tx_category,
            "zakelijk_flexedge": tx_zakelijk,
        }
        if tx_km > 0:
            new_tx["distance_km"] = tx_km
            new_tx["mode"] = tx_mode
        transactions.append(new_tx)
        _save(transactions)
        st.success(f"Uitgave toegevoegd: EUR {tx_amount:,.2f} — {tx_category}")
        st.rerun()

# ══════════════════════════════════════════════════════════════
# OVERZICHT PER CATEGORIE
# ══════════════════════════════════════════════════════════════

if ytd_txs:
    st.divider()
    st.markdown("#### Per categorie (YTD)")

    cat_df = pd.DataFrame(ytd_txs).groupby("category")["amount"].sum().sort_values(ascending=True).reset_index()
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
        height=max(180, len(cat_df) * 40),
        margin=dict(l=0, r=80, t=10, b=0),
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

# ══════════════════════════════════════════════════════════════
# ALLE TRANSACTIES
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Alle uitgaven")

if transactions:
    display_txs = sorted(transactions, key=lambda t: t.get("date", ""), reverse=True)
    display_df = pd.DataFrame(display_txs)

    # Ensure columns exist
    for col in ["date", "description", "amount", "category", "zakelijk_flexedge", "distance_km", "mode"]:
        if col not in display_df.columns:
            display_df[col] = "" if col in ("description", "category", "mode") else (False if col == "zakelijk_flexedge" else 0)

    st.dataframe(
        display_df[["date", "description", "amount", "category", "zakelijk_flexedge", "distance_km", "mode"]].rename(
            columns={
                "date": "Datum",
                "description": "Omschrijving",
                "amount": "Bedrag",
                "category": "Categorie",
                "zakelijk_flexedge": "Zakelijk FE",
                "distance_km": "km",
                "mode": "Vervoer",
            }
        ),
        use_container_width=True,
        hide_index=True,
        column_config={
            "Bedrag": st.column_config.NumberColumn(format="EUR %.2f"),
            "Zakelijk FE": st.column_config.CheckboxColumn(),
            "km": st.column_config.NumberColumn(format="%.0f"),
        },
    )

    # Delete button
    if st.button("Laatste uitgave verwijderen", type="secondary"):
        if transactions:
            removed = transactions.pop()
            _save(transactions)
            st.success(f"Verwijderd: {removed.get('description', '?')} (EUR {removed.get('amount', 0):,.2f})")
            st.rerun()
else:
    st.info("Nog geen uitgaven ingevoerd.")

# ══════════════════════════════════════════════════════════════
# DOORSTROOM NAAR EMISSIES
# ══════════════════════════════════════════════════════════════

zakelijk_reizen = [t for t in transactions if t.get("zakelijk_flexedge") and t.get("distance_km", 0) > 0]
if zakelijk_reizen:
    st.divider()
    st.markdown("#### Zakelijke reizen → FlexEdge BV emissies")
    st.caption("Deze reizen worden meegenomen in de Scope 3 Cat 6 berekening van FlexEdge BV.")

    travel_rows = []
    total_co2 = 0
    for t in zakelijk_reizen:
        km = t.get("distance_km", 0)
        mode = t.get("mode", "Trein")
        mode_key = TRAVEL_MODES.get(mode, "travel_train")
        factor = FACTORS.get(mode_key, 0.008)
        co2 = km * factor
        total_co2 += co2
        travel_rows.append({
            "Datum": t["date"],
            "Omschrijving": t.get("description", ""),
            "km": km,
            "Vervoer": mode,
            "kg CO₂e": co2,
        })

    st.dataframe(
        pd.DataFrame(travel_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "kg CO₂e": st.column_config.NumberColumn(format="%.1f"),
            "km": st.column_config.NumberColumn(format="%.0f"),
        },
    )
    st.metric("Totaal CO₂e (zakelijke reizen holding)", f"{total_co2:,.1f} kg")

# ══════════════════════════════════════════════════════════════
# BANKKOPPELING HOLDING
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Bankkoppeling")

holding_bank = _load_holding_bank_config(user)
holding_account_id = holding_bank.get("account_id", "")

if holding_account_id:
    # Show balance
    balance = get_balance_for_account(holding_account_id)
    if balance:
        st.success(f"Gekoppeld — Saldo: EUR {balance['amount']:,.2f} (per {balance.get('date', '?')})")
    else:
        st.warning("Rekening gekoppeld maar saldo niet beschikbaar. Consent mogelijk verlopen.")

    # Import transactions
    with st.expander("Banktransacties importeren"):
        import_period = st.selectbox("Periode", ["Laatste 30 dagen", "Laatste 90 dagen"], key="h_import_period")
        import_days = 30 if "30" in import_period else 90

        if st.button("Importeer transacties", key="import_bank_txs"):
            with st.spinner("Transacties ophalen..."):
                bank_txs = get_transactions_for_account(holding_account_id, days=import_days)
                outgoing = [t for t in bank_txs if t["amount"] < 0]

                if outgoing:
                    # Add to holding transactions (avoid duplicates)
                    existing_keys = {f"{t['date']}|{t['amount']}" for t in transactions}
                    added = 0
                    for tx in outgoing:
                        key = f"{tx['date']}|{tx['amount']}"
                        if key not in existing_keys:
                            transactions.append({
                                "date": tx["date"],
                                "amount": abs(tx["amount"]),
                                "description": tx["description"],
                                "category": "Overig",
                                "zakelijk_flexedge": False,
                            })
                            added += 1
                    if added:
                        _save(transactions)
                        st.success(f"{added} nieuwe transacties geïmporteerd.")
                        st.rerun()
                    else:
                        st.info("Geen nieuwe transacties gevonden.")
                else:
                    st.info("Geen uitgaande transacties in deze periode.")

    if st.button("Ontkoppel bankrekening", key="disconnect_holding_bank", type="secondary"):
        save_holding_bank_config(user, {})
        st.success("Bankrekening ontkoppeld.")
        st.rerun()

elif bank_configured():
    st.caption("Koppel je holding-bankrekening om transacties automatisch te importeren.")
    st.caption("Gebruikt dezelfde Enable Banking koppeling — je holding-data is alleen voor jou zichtbaar.")

    if st.button("Start bankkoppeling", key="start_holding_auth"):
        result = start_authorization()
        if result:
            st.session_state["_holding_auth_url"] = result["url"]
            st.session_state["_holding_auth_id"] = result.get("authorization_id")

    if "_holding_auth_url" in st.session_state:
        st.markdown(f"[Klik hier om in te loggen bij je bank]({st.session_state['_holding_auth_url']})")
        st.caption("Na autorisatie ontvang je een code. Plak deze hieronder.")
        auth_code = st.text_input("Autorisatiecode", key="holding_auth_code")
        if st.button("Koppel", key="complete_holding_auth"):
            session = complete_authorization(auth_code)
            if session and session.get("accounts"):
                account_uid = session["accounts"][0]
                save_holding_bank_config(user, {
                    "account_id": account_uid,
                    "session_id": session.get("session_id", ""),
                    "linked_at": date.today().isoformat(),
                })
                st.session_state.pop("_holding_auth_url", None)
                st.success(f"Bankrekening gekoppeld!")
                st.rerun()
            else:
                st.error("Kon rekening niet koppelen. Probeer opnieuw.")
else:
    st.info("Enable Banking niet geconfigureerd. Stel eerst de FlexEdge BV-koppeling in bij **Instellingen**.")
