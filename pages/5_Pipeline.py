"""Pipeline — Sales deals and conversion overview."""
from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.productive_api import get_deals, get_companies, build_lookup, safe_load

st.markdown("# Pipeline")

deals = safe_load(get_deals)
companies = safe_load(get_companies)
company_lookup = build_lookup(companies)

# Filter to open deals only
open_deals = [d for d in deals if not d["closed"]]

if open_deals:
    df = pd.DataFrame(open_deals)
    df["company"] = df["company_id"].map(company_lookup).fillna("Onbekend")

    total_pipeline = df["revenue"].sum()
    weighted = df["weighted_value"].sum()

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Open Deals", len(df))
    with c2:
        st.metric("Pipeline (totaal)", f"EUR {total_pipeline:,.0f}")
    with c3:
        st.metric("Pipeline (gewogen)", f"EUR {weighted:,.0f}")

    # By stage
    st.divider()
    st.markdown("#### Per Stage")
    stage_df = df.groupby("status").agg(
        Aantal=("id", "count"),
        Revenue=("revenue", "sum"),
        Gewogen=("weighted_value", "sum"),
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=stage_df["status"], y=stage_df["Gewogen"],
        marker_color="#003566",
        text=stage_df["Gewogen"].apply(lambda x: f"EUR {x:,.0f}"),
        textposition="outside",
        name="Gewogen revenue",
    ))
    fig.update_layout(
        height=300, margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="EUR (gewogen)",
        template="plotly_white",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Secondary: count per stage
    st.caption("Aantal deals per stage")
    stage_count = stage_df[["status", "Aantal"]].copy()
    st.dataframe(stage_count, use_container_width=True, hide_index=True)

    # Deal list
    st.divider()
    st.markdown("#### Alle Open Deals")
    display = df[["name", "company", "status", "revenue", "probability", "weighted_value"]].copy()
    display.columns = ["Deal", "Bedrijf", "Stage", "Revenue", "Prob %", "Gewogen"]
    display = display.sort_values("Prob %", ascending=False)
    display["Revenue"] = display["Revenue"].apply(lambda x: f"EUR {x:,.0f}" if x > 0 else "-")
    display["Gewogen"] = display["Gewogen"].apply(lambda x: f"EUR {x:,.0f}" if x > 0 else "-")
    st.dataframe(display, use_container_width=True, hide_index=True)
else:
    st.info("Geen open deals gevonden.")
