"""Resourcing — Weekly team allocation overview."""
from __future__ import annotations

from datetime import date

import streamlit as st
import pandas as pd

st.markdown("# Resourcing")
st.caption("Weekoverzicht: wie werkt waar? Bewerk de tabel voor de weekstart.")

today = date.today()
week_num = today.isocalendar()[1]

# ── Sidebar: team capacity ──
with st.sidebar:
    st.markdown("### Capaciteit (dagen/week)")
    cap_mick = st.number_input("Mick", value=4.0, step=0.5, key="rc_mick")
    cap_joris = st.number_input("Joris", value=1.0, step=0.5, key="rc_joris")
    cap_tessa = st.number_input("Tessa", value=4.0, step=0.5, key="rc_tessa")
    cap_gerben = st.number_input("Gerben", value=1.0, step=0.5, key="rc_gerben")

team = ["Mick", "Joris", "Tessa", "Gerben"]
capacities = [cap_mick, cap_joris, cap_tessa, cap_gerben]

billable = ["MECC", "KMWP", "Heras EED", "Hazeldonk", "Bright Data"]
internal = ["Sales", "Business", "Blueprint"]

data = {"Persoon": team, "Capaciteit": capacities}
for proj in billable + internal:
    data[proj] = [0.0] * len(team)

key = f"resourcing_w{week_num}"
if key not in st.session_state:
    st.session_state[key] = pd.DataFrame(data)

st.markdown(f"#### Week {week_num}")

edited = st.data_editor(
    st.session_state[key],
    use_container_width=True,
    hide_index=True,
    key=f"editor_{key}",
    column_config={
        "Persoon": st.column_config.TextColumn(disabled=True, width="small"),
        "Capaciteit": st.column_config.NumberColumn(disabled=True, format="%.1f", width="small"),
    },
)

if edited is not None:
    alloc_cols = [c for c in edited.columns if c not in ("Persoon", "Capaciteit")]
    edited["Totaal"] = edited[alloc_cols].sum(axis=1)
    edited["Vrij"] = edited["Capaciteit"] - edited["Totaal"]

    st.divider()
    st.markdown("#### Samenvatting")

    for _, row in edited.iterrows():
        name = row["Persoon"]
        alloc = row["Totaal"]
        cap = row["Capaciteit"]
        free = row["Vrij"]
        if free < 0:
            status, clr = "Overbezet", "red"
        elif free < 0.5:
            status, clr = "Vol", "orange"
        else:
            status, clr = f"{free:.1f}d vrij", "green"
        st.markdown(f"**{name}**: {alloc:.1f}/{cap:.1f} dagen — :{clr}[{status}]")

    # Billable vs internal
    st.divider()
    bill_total = edited[billable].sum().sum()
    int_total = edited[internal].sum().sum()
    grand = bill_total + int_total

    c1, c2 = st.columns(2)
    with c1:
        pct = bill_total / grand * 100 if grand > 0 else 0
        st.metric("Billable dagen", f"{bill_total:.1f}",
                  delta=f"{pct:.0f}% van totaal")
    with c2:
        pct2 = int_total / grand * 100 if grand > 0 else 0
        st.metric("Intern dagen", f"{int_total:.1f}",
                  delta=f"{pct2:.0f}% van totaal")

    # Per project totals
    st.divider()
    st.markdown("#### Per Project")
    proj_totals = edited[alloc_cols].sum().reset_index()
    proj_totals.columns = ["Project", "Dagen"]
    proj_totals = proj_totals[proj_totals["Dagen"] > 0].sort_values("Dagen", ascending=False)
    if not proj_totals.empty:
        st.dataframe(proj_totals, use_container_width=True, hide_index=True)
    else:
        st.info("Vul de tabel hierboven in om de resourcing te zien.")
