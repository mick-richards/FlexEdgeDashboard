"""Kostenplan — Monthly cost projection for runway calculation."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

st.markdown("# Kostenplan")
st.caption("Verwachte kosten per maand. Pas aan wanneer salarissen stijgen of eenmalige kosten bijkomen.")

COST_FILE = Path(__file__).parent.parent / "data" / "cost_plan.json"
COST_FILE.parent.mkdir(exist_ok=True)

MONTHS = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]
current_month = date.today().month - 1


def _load() -> dict:
    if COST_FILE.exists():
        return json.loads(COST_FILE.read_text(encoding="utf-8"))
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
        "one_offs": [],
    }


def _save(plan: dict) -> None:
    COST_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")


plan = _load()

# ══════════════════════════════════════════════════════════════
# MAANDELIJKSE KOSTEN
# ══════════════════════════════════════════════════════════════

st.markdown("#### Terugkerende kosten per maand")
st.caption("Elke cel is bewerkbaar. Pas salarissen, kantoorkosten etc. aan per maand.")

cost_data = {"Categorie": list(plan["categories"].keys())}
for i, m in enumerate(MONTHS):
    cost_data[m] = [vals[i] for vals in plan["categories"].values()]

# Add totals row
cost_data["Categorie"].append("TOTAAL")
for i, m in enumerate(MONTHS):
    cost_data[m].append(sum(vals[i] for vals in plan["categories"].values()))

cost_df = pd.DataFrame(cost_data)

edited = st.data_editor(
    cost_df,
    use_container_width=True,
    hide_index=True,
    key="cost_plan_editor",
    disabled=["Categorie"],
    column_config={
        "Categorie": st.column_config.TextColumn(width="medium"),
    },
)

if st.button("Opslaan", type="primary", key="save_costs"):
    if edited is not None:
        # Skip the TOTAAL row
        for _, row in edited.iterrows():
            cat = row["Categorie"]
            if cat == "TOTAAL":
                continue
            plan["categories"][cat] = [float(row[m]) for m in MONTHS]
        _save(plan)
        st.success("Kostenplan opgeslagen!")

# ══════════════════════════════════════════════════════════════
# EENMALIGE KOSTEN
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Eenmalige kosten")
st.caption("Kosten die je weet dat eraan komen — apparatuur, advieskosten, etc.")

one_offs = plan.get("one_offs", [])

with st.form("add_one_off", clear_on_submit=True):
    cols = st.columns([1, 2, 1, 1])
    with cols[0]:
        oo_month = st.selectbox("Maand", MONTHS, index=current_month)
    with cols[1]:
        oo_desc = st.text_input("Omschrijving")
    with cols[2]:
        oo_amount = st.number_input("Bedrag", min_value=0, step=100, key="oo_amt")
    with cols[3]:
        st.markdown("")
        st.markdown("")
        submitted = st.form_submit_button("Toevoegen")
    if submitted and oo_desc and oo_amount > 0:
        one_offs.append({"month": MONTHS.index(oo_month), "description": oo_desc, "amount": oo_amount})
        plan["one_offs"] = one_offs
        _save(plan)
        st.rerun()

if one_offs:
    oo_df = pd.DataFrame([
        {"Maand": MONTHS[oo["month"]], "Omschrijving": oo["description"], "Bedrag": f"EUR {oo['amount']:,.0f}"}
        for oo in one_offs
    ])
    st.dataframe(oo_df, use_container_width=True, hide_index=True)

    # Delete
    with st.expander("Verwijderen"):
        options = [f"{MONTHS[oo['month']]} — {oo['description']} (EUR {oo['amount']:,.0f})" for oo in one_offs]
        to_del = st.selectbox("Selecteer", options)
        if st.button("Verwijderen"):
            one_offs.pop(options.index(to_del))
            plan["one_offs"] = one_offs
            _save(plan)
            st.rerun()
else:
    st.info("Geen eenmalige kosten gepland.")

# ══════════════════════════════════════════════════════════════
# OVERZICHT GRAFIEK
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Totale kosten per maand (2026)")

monthly_recurring = []
monthly_oneoff = []
for m_idx in range(12):
    recurring = sum(vals[m_idx] for vals in plan["categories"].values())
    oneoff = sum(oo["amount"] for oo in one_offs if oo["month"] == m_idx)
    monthly_recurring.append(recurring)
    monthly_oneoff.append(oneoff)

fig = go.Figure()
fig.add_trace(go.Bar(
    x=MONTHS, y=monthly_recurring,
    name="Terugkerend",
    marker_color="#003566",
))
if any(v > 0 for v in monthly_oneoff):
    fig.add_trace(go.Bar(
        x=MONTHS, y=monthly_oneoff,
        name="Eenmalig",
        marker_color="#F4A261",
    ))

# Mark current month
fig.add_vline(x=current_month, line_dash="dot", line_color="#86868B",
              annotation_text="Nu")

fig.update_layout(
    height=350, margin=dict(l=0, r=0, t=10, b=0),
    yaxis_title="EUR", template="plotly_white",
    barmode="stack",
    legend=dict(orientation="h", y=1.1),
)
st.plotly_chart(fig, use_container_width=True)

# Annual total
annual = sum(monthly_recurring) + sum(monthly_oneoff)
remaining = sum(monthly_recurring[current_month:]) + sum(monthly_oneoff[current_month:])
c1, c2 = st.columns(2)
with c1:
    st.metric("Totaal 2026", f"EUR {annual:,.0f}")
with c2:
    st.metric("Resterend (vanaf nu)", f"EUR {remaining:,.0f}")
