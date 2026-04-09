"""Uitgaven — Actual expenses from bank transactions with editable categories and SBTi Scope 3 mapping."""
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
    "Kantoorartikelen", "Capital Goods", "Verzekeringen", "Reiskosten",
    "Telecom", "Belasting", "Bank", "Inhuur", "Marketing & acquisitie",
    "Opleiding", "Overig",
]

CATEGORY_RULES = {
    "Salarissen": ["loonheffing", "salaris", "dga", "pensioen", "netto loon"],
    "Boekhouder": ["slingerland"],
    "Software & tools": ["anthropic", "claude", "github", "streamlit", "zapier", "plaud",
                         "docusign", "think-cell", "microsoft 365", "norton", "cloudflare",
                         "productive", "miro", "canva", "notion", "figma", "google workspace",
                         "adobe", "gamma", "saas", "licentie"],
    "Capital Goods": ["laptop", "macbook", "thinkpad", "dell ", "lenovo", "monitor",
                      "ipad", "iphone", "printer", "server", "hardware", "coolblue",
                      "mediamarkt", "bol.com"],
    "Kantoorartikelen": ["papier", "inkt", "toner", "pennen", "post-it", "envelop",
                         "bruna", "staples", "office depot", "hema kantoor",
                         "bureau-accessoire", "ordner"],
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

# ── SBTi Scope 3 mapping ──
# Maps each expense category to SBTi Scope 3 category + spend-based emission factor
# Sources: EXIOBASE v3.8.2, DEFRA 2024, co2emissiefactoren.nl
SBTI_MAPPING = {
    "Salarissen":           {"scope3_cat": "n.v.t.",                            "factor": 0.0,   "note": "Geen Scope 3 — eigen personeel"},
    "Boekhouder":           {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.12,  "note": "Professionele dienstverlening"},
    "Software & tools":     {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.08,  "note": "SaaS / digitale diensten"},
    "Kantoor":              {"scope3_cat": "Cat 8: Upstream Leased Assets",     "factor": 0.10,  "note": "Huur kantoorruimte"},
    "Kantoorartikelen":     {"scope3_cat": "Cat 1: Purchased Goods",            "factor": 0.25,  "note": "Papier, inkt, kantoorbenodigdheden"},
    "Capital Goods":        {"scope3_cat": "Cat 2: Capital Goods",              "factor": 0.25,  "note": "IT-apparatuur, afschrijfbare assets"},
    "Verzekeringen":        {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.07,  "note": "Financiële dienstverlening"},
    "Reiskosten":           {"scope3_cat": "Cat 6: Business Travel",            "factor": 0.15,  "note": "Gemiddelde OV + auto (spend-based)"},
    "Telecom":              {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.06,  "note": "Telecomdiensten"},
    "Belasting":            {"scope3_cat": "n.v.t.",                            "factor": 0.0,   "note": "Geen Scope 3 — overheidsheffingen"},
    "Bank":                 {"scope3_cat": "n.v.t.",                            "factor": 0.0,   "note": "Geen Scope 3 — bankkosten"},
    "Inhuur":               {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.12,  "note": "Ingehuurde professionals"},
    "Marketing & acquisitie": {"scope3_cat": "Cat 1: Purchased Services",       "factor": 0.10,  "note": "Marketing, events, hospitality"},
    "Opleiding":            {"scope3_cat": "Cat 1: Purchased Services",         "factor": 0.10,  "note": "Training & ontwikkeling"},
    "Overig":               {"scope3_cat": "Cat 1: Purchased Goods & Services", "factor": 0.15,  "note": "Gemiddelde spend-based factor"},
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

# SBTi mapping columns
outgoing["scope3_cat"] = outgoing["category"].map(
    lambda c: SBTI_MAPPING.get(c, SBTI_MAPPING["Overig"])["scope3_cat"]
)
outgoing["ef_kg_per_eur"] = outgoing["category"].map(
    lambda c: SBTI_MAPPING.get(c, SBTI_MAPPING["Overig"])["factor"]
)
outgoing["co2e_kg"] = outgoing["amount"] * outgoing["ef_kg_per_eur"]

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

total_out = outgoing["amount"].sum()
total_in = incoming["amount"].sum()
total_co2e = outgoing["co2e_kg"].sum()

c1, c2, c3, c4 = st.columns(4)
with c1:
    st.metric("Totaal uitgegeven", f"EUR {total_out:,.0f}")
with c2:
    st.metric("Totaal ontvangen", f"EUR {total_in:,.0f}")
with c3:
    netto = total_in - total_out
    st.metric("Netto", f"EUR {netto:,.0f}",
              delta="Positief" if netto > 0 else "Negatief",
              delta_color="normal" if netto > 0 else "inverse")
with c4:
    if total_co2e >= 1000:
        st.metric("CO₂e (Scope 3)", f"{total_co2e / 1000:,.1f} ton")
    else:
        st.metric("CO₂e (Scope 3)", f"{total_co2e:,.0f} kg")

# ══════════════════════════════════════════════════════════════
# TABS: Categorieën | SBTi Scope 3
# ══════════════════════════════════════════════════════════════

tab_cat, tab_sbti = st.tabs(["Per Categorie", "SBTi Scope 3"])

# ── Tab 1: Per Categorie (bestaand) ──
with tab_cat:
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

# ── Tab 2: SBTi Scope 3 ──
with tab_sbti:
    st.caption("Spend-based emissieberekening per SBTi Scope 3 categorie (EXIOBASE/DEFRA factoren)")

    # Aggregate by Scope 3 category
    scope3_agg = outgoing[outgoing["ef_kg_per_eur"] > 0].groupby("scope3_cat").agg(
        Uitgaven=("amount", "sum"),
        CO2e_kg=("co2e_kg", "sum"),
    ).sort_values("CO2e_kg", ascending=True).reset_index()
    scope3_agg.columns = ["SBTi Categorie", "Uitgaven", "CO₂e (kg)"]

    if not scope3_agg.empty:
        # Chart
        fig_s3 = go.Figure()
        fig_s3.add_trace(go.Bar(
            y=scope3_agg["SBTi Categorie"],
            x=scope3_agg["CO₂e (kg)"],
            orientation="h",
            marker_color="#2A9D8F",
            text=scope3_agg.apply(
                lambda r: f"{r['CO₂e (kg)']:,.0f} kg  (EUR {r['Uitgaven']:,.0f})", axis=1
            ),
            textposition="outside",
        ))
        fig_s3.update_layout(
            height=max(200, len(scope3_agg) * 50),
            margin=dict(l=0, r=140, t=10, b=0),
            xaxis_title="kg CO₂e",
            template="plotly_white",
        )
        st.plotly_chart(fig_s3, use_container_width=True)

        # Summary metrics
        s1, s2, s3 = st.columns(3)
        cat1_co2 = outgoing[outgoing["scope3_cat"].str.startswith("Cat 1")]["co2e_kg"].sum()
        cat2_co2 = outgoing[outgoing["scope3_cat"].str.startswith("Cat 2")]["co2e_kg"].sum()
        cat6_co2 = outgoing[outgoing["scope3_cat"].str.startswith("Cat 6")]["co2e_kg"].sum()
        with s1:
            st.metric("Cat 1: Purchased G&S", f"{cat1_co2:,.0f} kg CO₂e")
        with s2:
            st.metric("Cat 2: Capital Goods", f"{cat2_co2:,.0f} kg CO₂e")
        with s3:
            st.metric("Cat 6: Business Travel", f"{cat6_co2:,.0f} kg CO₂e")

        # Detailed table
        st.markdown("##### Emissiefactoren per categorie")
        ef_rows = []
        for cat_name, mapping in SBTI_MAPPING.items():
            if mapping["factor"] > 0:
                cat_total = outgoing[outgoing["category"] == cat_name]["amount"].sum()
                cat_co2 = cat_total * mapping["factor"]
                if cat_total > 0:
                    ef_rows.append({
                        "Categorie": cat_name,
                        "SBTi": mapping["scope3_cat"],
                        "Factor (kg/EUR)": mapping["factor"],
                        "Uitgaven (EUR)": cat_total,
                        "CO₂e (kg)": cat_co2,
                        "Toelichting": mapping["note"],
                    })
        if ef_rows:
            ef_df = pd.DataFrame(ef_rows).sort_values("CO₂e (kg)", ascending=False)
            st.dataframe(
                ef_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Uitgaven (EUR)": st.column_config.NumberColumn(format="EUR %.0f"),
                    "CO₂e (kg)": st.column_config.NumberColumn(format="%.1f"),
                    "Factor (kg/EUR)": st.column_config.NumberColumn(format="%.2f"),
                },
            )
    else:
        st.info("Geen relevante Scope 3 uitgaven in deze periode.")

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
# ALLE TRANSACTIES (met bewerkbare categorie + SBTi kolom)
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Alle Uitgaven")
st.caption("Klik op een categorie om deze aan te passen. De SBTi-classificatie past zich automatisch aan.")

display = outgoing[["date", "description", "amount", "category", "scope3_cat", "co2e_kg", "tx_key"]].copy()
display = display.sort_values("date", ascending=False).reset_index(drop=True)

edited_df = st.data_editor(
    display[["date", "description", "amount", "category", "scope3_cat", "co2e_kg"]].rename(
        columns={
            "date": "Datum",
            "description": "Omschrijving",
            "amount": "Bedrag",
            "category": "Categorie",
            "scope3_cat": "SBTi Scope 3",
            "co2e_kg": "CO₂e (kg)",
        }
    ),
    use_container_width=True,
    hide_index=True,
    key="tx_editor",
    disabled=["Datum", "Omschrijving", "Bedrag", "SBTi Scope 3", "CO₂e (kg)"],
    column_config={
        "Categorie": st.column_config.SelectboxColumn(
            options=ALL_CATEGORIES,
            width="medium",
        ),
        "Bedrag": st.column_config.NumberColumn(format="EUR %.2f"),
        "CO₂e (kg)": st.column_config.NumberColumn(format="%.1f"),
        "SBTi Scope 3": st.column_config.TextColumn(width="medium"),
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
