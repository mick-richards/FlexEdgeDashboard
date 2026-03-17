"""Omzet & Facturen — Revenue tracking and budget burn."""
from __future__ import annotations

from datetime import date

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_invoices, get_budgets, get_projects, build_lookup

st.markdown("# Omzet & Facturen")

today = date.today()
year_start = today.replace(month=1, day=1)

invoices = get_invoices()
budgets = get_budgets()
projects = get_projects()
project_lookup = build_lookup(projects)

# ── Monthly revenue chart ──
paid = [i for i in invoices if i["status"] == "paid" and i.get("paid_date")]

if paid:
    rev_df = pd.DataFrame(paid)
    rev_df["month"] = pd.to_datetime(rev_df["paid_date"]).dt.to_period("M").astype(str)
    monthly = rev_df.groupby("month")["total_with_tax"].sum().reset_index()
    monthly.columns = ["Maand", "Omzet"]
    monthly = monthly.tail(6)

    # Sidebar fixed costs for break-even line
    total_fixed = (
        st.session_state.get("s_salary", 8500)
        + st.session_state.get("s_office", 1500)
        + st.session_state.get("s_other", 500)
    )

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=monthly["Maand"], y=monthly["Omzet"],
        marker_color="#003566",
        text=monthly["Omzet"].apply(lambda x: f"EUR {x:,.0f}"),
        textposition="outside",
    ))
    fig.add_hline(y=total_fixed, line_dash="dash", line_color="#E63946",
                  annotation_text=f"Break-even: EUR {total_fixed:,.0f}")
    fig.update_layout(
        title="Maandelijkse Omzet (betaald)",
        height=350, margin=dict(l=0, r=0, t=40, b=0),
        yaxis_title="EUR", template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # YTD summary
    ytd_paid = [i for i in invoices if i["status"] == "paid"
                and (i.get("paid_date") or "") >= year_start.isoformat()]
    total_ytd = sum(i["total_with_tax"] for i in ytd_paid)
    avg_monthly = total_ytd / max(today.month, 1)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Omzet YTD", f"EUR {total_ytd:,.0f}")
    with c2:
        st.metric("Gem. per maand", f"EUR {avg_monthly:,.0f}")
else:
    st.info("Geen betaalde facturen gevonden.")

# ── All invoices 2026 ──
st.divider()
st.markdown("#### Alle Facturen 2026")
inv_2026 = [i for i in invoices if (i.get("date") or "") >= "2026-01-01"]
if inv_2026:
    df = pd.DataFrame(inv_2026)
    df = df.sort_values("date", ascending=False)
    df = df[["number", "date", "due_date", "paid_date", "total_with_tax", "status"]]
    df.columns = ["Nummer", "Datum", "Vervaldatum", "Betaald", "Bedrag", "Status"]
    df["Bedrag"] = df["Bedrag"].apply(lambda x: f"EUR {x:,.2f}")
    st.dataframe(df, use_container_width=True, hide_index=True)

# ── Budget burn ──
st.divider()
st.markdown("#### Budget Burn per Project")
active_budgets = [b for b in budgets if b["total_hours"] > 0]
if active_budgets:
    bdf = pd.DataFrame(active_budgets)
    bdf["project"] = bdf["project_id"].map(project_lookup).fillna("Onbekend")
    bdf["burn_pct"] = (bdf["spent_hours"] / bdf["total_hours"] * 100).clip(0, 150)
    bdf = bdf.sort_values("burn_pct", ascending=True)

    fig_burn = go.Figure()
    fig_burn.add_trace(go.Bar(
        y=bdf["name"], x=bdf["burn_pct"],
        orientation="h",
        marker_color=bdf["burn_pct"].apply(
            lambda x: "#E63946" if x > 90 else "#F4A261" if x > 70 else "#003566"
        ),
        text=bdf.apply(
            lambda r: f"{r['spent_hours']:.0f}/{r['total_hours']:.0f}u ({r['burn_pct']:.0f}%)",
            axis=1,
        ),
        textposition="outside",
    ))
    fig_burn.add_vline(x=100, line_dash="dash", line_color="#E63946")
    fig_burn.update_layout(
        height=max(250, len(active_budgets) * 40),
        margin=dict(l=0, r=100, t=10, b=0),
        xaxis_title="Budget verbruikt (%)", template="plotly_white",
    )
    st.plotly_chart(fig_burn, use_container_width=True)
else:
    st.info("Geen budgetten met uren gevonden.")
