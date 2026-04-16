"""Emissies — GHG Protocol rapportage: Scope 1, 2 en 3."""
from __future__ import annotations

from datetime import date

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from services.emissions import (
    FACTORS, COMMUTE_MODES, TRAVEL_MODES,
    load_scope1, save_scope1,
    load_scope2, save_scope2,
    load_commute, save_commute,
    load_travel_log, save_travel_log,
    load_holding_travel,
    calc_scope1, calc_scope2,
    build_summary,
)

# ── Colors ──
CLR_S1 = "#E63946"    # Scope 1 — red
CLR_S2 = "#F4A261"    # Scope 2 — orange
CLR_S3 = "#2A9D8F"    # Scope 3 — teal
CLR_PRIMARY = "#003566"

st.markdown("# Emissies")
st.caption("GHG Protocol rapportage — Scope 1, 2 en 3 voor FlexEdge BV.")

today = date.today()
current_year = today.year

# ── Load all data ──
scope1_data = load_scope1()
scope2_data = load_scope2()
commute_employees = load_commute()
travel_trips = load_travel_log() + load_holding_travel()

# Try to load Scope 3 expense data from Uitgaven
expense_scope3 = {}
try:
    from services.productive_api import safe_load, get_invoices
    from services.bank_api import is_configured as bank_configured, get_transactions
    if bank_configured():
        from pages import _uitgaven_helpers  # noqa: F401 — not available, skip
except Exception:
    pass

# Default FTE count
fte_count = st.sidebar.number_input("FTE (voor afvalschatting)", value=2.5, step=0.5, min_value=0.5, key="fte_count")

# Build summary
summary = build_summary(
    scope1_data=scope1_data,
    scope2_data=scope2_data,
    commute_employees=commute_employees,
    travel_trips=[t for t in travel_trips if t.get("date", "").startswith(str(current_year))],
    fte_count=fte_count,
    expense_scope3=expense_scope3,
)

# ══════════════════════════════════════════════════════════════
# KPIs
# ══════════════════════════════════════════════════════════════

s1 = summary["scope1"]["total"]
s2_loc = summary["scope2"]["location_based"]
s2_mkt = summary["scope2"]["market_based"]
s3 = summary["scope3"]["total"]
total_loc = summary["total_location"]

c1, c2, c3, c4 = st.columns(4)
with c1:
    if total_loc >= 1000:
        st.metric("Totaal CO₂e", f"{total_loc / 1000:,.2f} ton")
    else:
        st.metric("Totaal CO₂e", f"{total_loc:,.0f} kg")
with c2:
    st.metric("Scope 1", f"{s1:,.0f} kg", help="Directe emissies (gasverbruik)")
with c3:
    st.metric("Scope 2", f"{s2_loc:,.0f} kg", help="Indirecte energie (elektriciteit)")
with c4:
    st.metric("Scope 3", f"{s3:,.0f} kg", help="Waardeketen-emissies")

# ══════════════════════════════════════════════════════════════
# SCOPE OVERVIEW — Donut chart + breakdown table
# ══════════════════════════════════════════════════════════════

st.divider()
col_chart, col_table = st.columns([1, 1.5], gap="large")

with col_chart:
    st.markdown("#### Verdeling per scope")
    if total_loc > 0:
        fig_donut = go.Figure(data=[go.Pie(
            labels=["Scope 1", "Scope 2", "Scope 3"],
            values=[s1, s2_loc, s3],
            marker_colors=[CLR_S1, CLR_S2, CLR_S3],
            hole=0.5,
            textinfo="label+percent",
            textposition="outside",
        )])
        fig_donut.update_layout(
            height=320, margin=dict(l=20, r=20, t=20, b=20),
            showlegend=False,
        )
        st.plotly_chart(fig_donut, use_container_width=True)
    else:
        st.info("Nog geen emissiedata ingevoerd.")

with col_table:
    st.markdown("#### Detailoverzicht")
    s3_data = summary["scope3"]
    rows = [
        {"Scope": "1", "Categorie": "Gasverbruik kantoor", "kg CO₂e": s1, "Bron": "Invoer meterstanden"},
        {"Scope": "2", "Categorie": "Elektriciteit (location-based)", "kg CO₂e": s2_loc, "Bron": "Invoer meterstanden"},
        {"Scope": "3.1", "Categorie": "Purchased Goods & Services", "kg CO₂e": s3_data["cat1_purchased_goods_services"], "Bron": "Banktransacties"},
        {"Scope": "3.2", "Categorie": "Capital Goods", "kg CO₂e": s3_data["cat2_capital_goods"], "Bron": "Banktransacties"},
        {"Scope": "3.3", "Categorie": "Fuel & Energy (WTT)", "kg CO₂e": s3_data["cat3_fuel_energy_wtt"], "Bron": "Berekend (15%/10%)"},
        {"Scope": "3.5", "Categorie": "Afval kantoor", "kg CO₂e": s3_data["cat5_waste"], "Bron": f"Forfaitair ({fte_count:.1f} FTE)"},
        {"Scope": "3.6", "Categorie": "Zakelijke reizen", "kg CO₂e": s3_data["cat6_business_travel"], "Bron": "Reislog"},
        {"Scope": "3.7", "Categorie": "Woon-werkverkeer", "kg CO₂e": s3_data["cat7_commuting"], "Bron": "Invoer medewerkers"},
        {"Scope": "3.8", "Categorie": "Upstream Leased Assets", "kg CO₂e": s3_data["cat8_leased_assets"], "Bron": "Banktransacties"},
    ]
    detail_df = pd.DataFrame(rows)
    detail_df = detail_df[detail_df["kg CO₂e"] > 0] if total_loc > 0 else detail_df
    st.dataframe(
        detail_df,
        use_container_width=True,
        hide_index=True,
        column_config={"kg CO₂e": st.column_config.NumberColumn(format="%.1f")},
    )

    if s2_mkt != s2_loc:
        st.caption(f"Market-based Scope 2: {s2_mkt:,.0f} kg CO₂e"
                   + (" (groene stroom)" if s2_mkt == 0 else ""))

# ══════════════════════════════════════════════════════════════
# DATA INVOER — Tabs voor Scope 1, 2, woon-werkverkeer, reizen
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Data invoer")

tab_s1, tab_s2, tab_commute, tab_travel = st.tabs([
    "Scope 1: Gas", "Scope 2: Elektriciteit", "Woon-werkverkeer", "Zakelijke reizen"
])

MONTHS = ["Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dec"]

# ── Scope 1: Gas ──
with tab_s1:
    st.caption(f"Gasverbruik kantoor {current_year} (m³ per maand). Emissiefactor: {FACTORS['gas_m3']} kg CO₂e/m³.")

    gas_values = []
    for i, month_name in enumerate(MONTHS):
        month_key = f"{current_year}-{i + 1:02d}"
        existing = scope1_data.get(month_key, {}).get("gas_m3", 0.0)
        gas_values.append({"Maand": month_name, "Gas (m³)": existing, "_key": month_key})

    gas_df = pd.DataFrame(gas_values)
    edited_gas = st.data_editor(
        gas_df[["Maand", "Gas (m³)"]],
        use_container_width=True,
        hide_index=True,
        key="gas_editor",
        disabled=["Maand"],
        column_config={"Gas (m³)": st.column_config.NumberColumn(min_value=0, step=1, format="%.0f")},
    )

    if st.button("Opslaan", key="save_gas"):
        new_data = {}
        for idx, row in edited_gas.iterrows():
            month_key = gas_values[idx]["_key"]
            val = row["Gas (m³)"]
            if val and val > 0:
                new_data[month_key] = {"gas_m3": float(val)}
        save_scope1(new_data)
        st.success("Gasverbruik opgeslagen.")
        st.rerun()

# ── Scope 2: Elektriciteit ──
with tab_s2:
    st.caption(f"Elektriciteitsverbruik kantoor {current_year} (kWh per maand).")

    green_default = scope2_data.get(f"{current_year}-01", {}).get("green", False)
    green_power = st.checkbox("Groene stroom (GoO-certificaten)", value=green_default, key="green_power")
    if green_power:
        st.caption(f"Market-based: 0 kg CO₂e/kWh | Location-based: {FACTORS['electricity_kwh_location']} kg CO₂e/kWh")
    else:
        st.caption(f"Emissiefactor: {FACTORS['electricity_kwh_location']} kg CO₂e/kWh (NL grid 2024)")

    elec_values = []
    for i, month_name in enumerate(MONTHS):
        month_key = f"{current_year}-{i + 1:02d}"
        existing = scope2_data.get(month_key, {}).get("kwh", 0.0)
        elec_values.append({"Maand": month_name, "Elektriciteit (kWh)": existing, "_key": month_key})

    elec_df = pd.DataFrame(elec_values)
    edited_elec = st.data_editor(
        elec_df[["Maand", "Elektriciteit (kWh)"]],
        use_container_width=True,
        hide_index=True,
        key="elec_editor",
        disabled=["Maand"],
        column_config={"Elektriciteit (kWh)": st.column_config.NumberColumn(min_value=0, step=1, format="%.0f")},
    )

    if st.button("Opslaan", key="save_elec"):
        new_data = {}
        for idx, row in edited_elec.iterrows():
            month_key = elec_values[idx]["_key"]
            val = row["Elektriciteit (kWh)"]
            if val and val > 0:
                new_data[month_key] = {"kwh": float(val), "green": green_power}
        save_scope2(new_data)
        st.success("Elektriciteitsverbruik opgeslagen.")
        st.rerun()

# ── Woon-werkverkeer ──
with tab_commute:
    st.caption("Vaste gegevens per medewerker. Berekening: afstand × 2 (retour) × werkdagen × weken × emissiefactor.")

    if not commute_employees:
        commute_employees = [
            {"name": "Tessa", "distance_km": 0, "days_per_week": 4, "mode": "Trein (NS)", "weeks_per_year": 46},
        ]

    commute_df = pd.DataFrame(commute_employees)
    display_cols = ["name", "distance_km", "days_per_week", "mode", "weeks_per_year"]
    for col in display_cols:
        if col not in commute_df.columns:
            commute_df[col] = "" if col in ("name", "mode") else 0

    edited_commute = st.data_editor(
        commute_df[display_cols].rename(columns={
            "name": "Naam",
            "distance_km": "Afstand (km, enkel)",
            "days_per_week": "Dagen/week",
            "mode": "Vervoermiddel",
            "weeks_per_year": "Werkweken/jaar",
        }),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="commute_editor",
        column_config={
            "Vervoermiddel": st.column_config.SelectboxColumn(options=list(COMMUTE_MODES.keys()), width="medium"),
            "Afstand (km, enkel)": st.column_config.NumberColumn(min_value=0, step=1, format="%.0f"),
            "Dagen/week": st.column_config.NumberColumn(min_value=0, max_value=5, step=1),
            "Werkweken/jaar": st.column_config.NumberColumn(min_value=0, max_value=52, step=1),
        },
    )

    if st.button("Opslaan", key="save_commute"):
        employees = []
        for _, row in edited_commute.iterrows():
            if row.get("Naam"):
                employees.append({
                    "name": row["Naam"],
                    "distance_km": float(row.get("Afstand (km, enkel)", 0) or 0),
                    "days_per_week": int(row.get("Dagen/week", 0) or 0),
                    "mode": row.get("Vervoermiddel", "Trein (NS)"),
                    "weeks_per_year": int(row.get("Werkweken/jaar", 46) or 46),
                })
        save_commute(employees)
        st.success("Woon-werkverkeer opgeslagen.")
        st.rerun()

    # Preview
    if commute_employees and any(e.get("distance_km", 0) > 0 for e in commute_employees):
        st.markdown("##### Voorbeeldberekening")
        for emp in commute_employees:
            dist = emp.get("distance_km", 0)
            if dist > 0:
                days = emp.get("days_per_week", 0)
                weeks = emp.get("weeks_per_year", 46)
                mode = emp.get("mode", "Trein (NS)")
                mode_key = COMMUTE_MODES.get(mode, "commute_train")
                factor = FACTORS[mode_key]
                annual = dist * 2 * days * weeks * factor
                st.caption(
                    f"**{emp['name']}**: {dist} km × 2 × {days} dgn × {weeks} wkn × {factor} = "
                    f"**{annual:,.0f} kg CO₂e/jaar**"
                )

# ── Zakelijke reizen ──
with tab_travel:
    st.caption("Handmatige invoer + agenda-scan. Reizen uit holdings worden automatisch meegenomen.")

    # ── Calendar scan ──
    st.markdown("##### Agenda scannen")
    scan_col1, scan_col2, scan_col3 = st.columns([1, 1, 1])
    with scan_col1:
        scan_from = st.date_input("Van", value=today.replace(day=1), key="scan_from")
    with scan_col2:
        scan_to = st.date_input("Tot", value=today, key="scan_to")
    with scan_col3:
        st.markdown("")
        st.markdown("")
        do_scan = st.button("Scan agenda", key="scan_calendar", type="primary")

    if do_scan:
        st.info(
            "De agenda-scan werkt via Claude Code. Gebruik `/assistant` of vraag Claude "
            "om je agenda te scannen voor de geselecteerde periode. De resultaten verschijnen "
            "hier automatisch."
        )
        # Store scan request for reference
        st.session_state["_scan_requested"] = {
            "from": scan_from.isoformat(),
            "to": scan_to.isoformat(),
        }

    # Load scan results from file (written by /assistant or scan_calendar.py)
    _scan_file = Path(__file__).parent.parent / "data" / "scan_results.json"
    if _scan_file.exists() and "_scan_results" not in st.session_state:
        import json as _json
        _scan_data = _json.loads(_scan_file.read_text(encoding="utf-8"))
        if _scan_data.get("results"):
            st.session_state["_scan_results"] = _scan_data["results"]

    # Process scan results (stored in session state by /assistant or manual trigger)
    if "_scan_results" in st.session_state and st.session_state["_scan_results"]:
        scan_results = st.session_state["_scan_results"]
        st.markdown(f"##### Gevonden reizen ({len(scan_results)})")

        for i, trip in enumerate(scan_results):
            with st.container():
                rc1, rc2, rc3, rc4, rc5 = st.columns([2, 1, 1, 1, 0.5])
                with rc1:
                    st.text(f"{trip['date']} — {trip['description']}")
                with rc2:
                    trip["distance_km"] = st.number_input(
                        "km", value=int(trip.get("distance_km", 0)),
                        min_value=0, step=5, key=f"scan_km_{i}",
                    )
                with rc3:
                    modes = list(TRAVEL_MODES.keys())
                    default_idx = modes.index(trip.get("mode", "Trein")) if trip.get("mode", "Trein") in modes else 0
                    trip["mode"] = st.selectbox("Vervoer", modes, index=default_idx, key=f"scan_mode_{i}")
                with rc4:
                    co2 = trip["distance_km"] * FACTORS.get(TRAVEL_MODES.get(trip["mode"], "travel_train"), 0.008)
                    st.metric("CO₂e", f"{co2:.1f} kg")
                with rc5:
                    trip["_include"] = st.checkbox("", value=trip.get("distance_km", 0) > 0, key=f"scan_inc_{i}")

        if st.button("Geselecteerde toevoegen aan reislog", key="add_scanned"):
            existing = load_travel_log()
            existing_keys = {(t["date"], t["description"]) for t in existing}
            added = 0
            for trip in scan_results:
                if trip.get("_include") and trip.get("distance_km", 0) > 0:
                    key = (trip["date"], trip["description"])
                    if key not in existing_keys:
                        existing.append({
                            "date": trip["date"],
                            "description": trip["description"],
                            "distance_km": float(trip["distance_km"]),
                            "mode": trip["mode"],
                            "source": "Agenda",
                        })
                        added += 1
            save_travel_log(existing)
            st.session_state.pop("_scan_results", None)
            st.success(f"{added} reis(zen) toegevoegd.")
            st.rerun()

        if st.button("Verwijder scanresultaten", key="clear_scan", type="secondary"):
            st.session_state.pop("_scan_results", None)
            st.rerun()

    st.divider()

    # ── Existing travel log (manual + scanned) ──
    st.markdown("##### Reislog")

    # Combine direct travel log + holding travel for display
    direct_trips = load_travel_log()
    holding_trips = load_holding_travel()
    all_display_trips = direct_trips + holding_trips

    trip_cols = ["date", "description", "distance_km", "mode", "source"]
    if not direct_trips:
        travel_df = pd.DataFrame(columns=trip_cols)
    else:
        travel_df = pd.DataFrame(direct_trips)
        for col in trip_cols:
            if col not in travel_df.columns:
                travel_df[col] = "" if col in ("description", "mode", "source") else 0

    edited_trips = st.data_editor(
        travel_df[trip_cols].rename(columns={
            "date": "Datum",
            "description": "Omschrijving",
            "distance_km": "Afstand (km)",
            "mode": "Vervoermiddel",
            "source": "Bron",
        }),
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        key="travel_editor",
        column_config={
            "Datum": st.column_config.TextColumn(width="small"),
            "Vervoermiddel": st.column_config.SelectboxColumn(options=list(TRAVEL_MODES.keys()), width="medium"),
            "Afstand (km)": st.column_config.NumberColumn(min_value=0, step=1, format="%.0f"),
            "Bron": st.column_config.SelectboxColumn(
                options=["Handmatig", "Agenda", "Holding"],
                default="Handmatig",
                width="small",
            ),
        },
    )

    if st.button("Opslaan", key="save_travel"):
        trips = []
        for _, row in edited_trips.iterrows():
            if row.get("Datum") and row.get("Afstand (km)", 0) > 0:
                trips.append({
                    "date": row["Datum"],
                    "description": row.get("Omschrijving", ""),
                    "distance_km": float(row.get("Afstand (km)", 0)),
                    "mode": row.get("Vervoermiddel", "Trein"),
                    "source": row.get("Bron", "Handmatig"),
                })
        save_travel_log(trips)
        st.success(f"{len(trips)} reis(zen) opgeslagen.")
        st.rerun()

    # Show holding trips (read-only)
    if holding_trips:
        st.markdown("##### Reizen vanuit holdings")
        st.caption("Automatisch meegenomen — beheer via de Holding-pagina.")
        ht_df = pd.DataFrame(holding_trips)[trip_cols].rename(columns={
            "date": "Datum", "description": "Omschrijving",
            "distance_km": "Afstand (km)", "mode": "Vervoermiddel", "source": "Bron",
        })
        st.dataframe(ht_df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════
# MAANDTREND (gestapeld: Scope 1 + 2 + 3)
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Maandtrend")

s1_monthly = calc_scope1(scope1_data)
s2_monthly = calc_scope2(scope2_data)

if s1_monthly or s2_monthly:
    all_months = sorted(set(list(s1_monthly.keys()) + list(s2_monthly.keys())))
    trend_data = []
    for m in all_months:
        trend_data.append({
            "Maand": m,
            "Scope 1": s1_monthly.get(m, 0),
            "Scope 2": s2_monthly.get(m, {}).get("location_based", 0) if isinstance(s2_monthly.get(m), dict) else 0,
        })
    trend_df = pd.DataFrame(trend_data)

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Bar(x=trend_df["Maand"], y=trend_df["Scope 1"],
                               name="Scope 1", marker_color=CLR_S1))
    fig_trend.add_trace(go.Bar(x=trend_df["Maand"], y=trend_df["Scope 2"],
                               name="Scope 2", marker_color=CLR_S2))
    fig_trend.update_layout(
        barmode="stack", height=300,
        margin=dict(l=0, r=0, t=10, b=0),
        yaxis_title="kg CO₂e", template="plotly_white",
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig_trend, use_container_width=True)
else:
    st.info("Voer maandelijkse gas- en elektriciteitsdata in om de trend te zien.")

# ══════════════════════════════════════════════════════════════
# GHG RAPPORT EXPORT
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Rapportage export")

exp_col1, exp_col2 = st.columns([2, 1])
with exp_col1:
    st.caption("Download een GHG Protocol-conform overzicht als CSV. Bevat alle scopes, categorieën en emissiefactoren.")
with exp_col2:
    # Build export data
    s3_data = summary["scope3"]
    export_rows = [
        {"Scope": "1", "Categorie": "Aardgas (kantoor)", "Eenheid": "m³", "Verbruik": sum(v.get("gas_m3", 0) for v in scope1_data.values()), "Emissiefactor": FACTORS["gas_m3"], "Factor eenheid": "kg CO₂e/m³", "kg CO₂e": s1, "Bron factor": "co2emissiefactoren.nl 2024"},
        {"Scope": "2 (location)", "Categorie": "Elektriciteit", "Eenheid": "kWh", "Verbruik": sum(v.get("kwh", 0) for v in scope2_data.values()), "Emissiefactor": FACTORS["electricity_kwh_location"], "Factor eenheid": "kg CO₂e/kWh", "kg CO₂e": s2_loc, "Bron factor": "CBS/RVO 2024"},
        {"Scope": "2 (market)", "Categorie": "Elektriciteit", "Eenheid": "kWh", "Verbruik": sum(v.get("kwh", 0) for v in scope2_data.values()), "Emissiefactor": 0.0 if any(v.get("green") for v in scope2_data.values()) else FACTORS["electricity_kwh_location"], "Factor eenheid": "kg CO₂e/kWh", "kg CO₂e": s2_mkt, "Bron factor": "Market-based (GoO)"},
        {"Scope": "3.1", "Categorie": "Purchased Goods & Services", "Eenheid": "EUR", "Verbruik": "", "Emissiefactor": "diverse", "Factor eenheid": "kg CO₂e/EUR", "kg CO₂e": s3_data["cat1_purchased_goods_services"], "Bron factor": "EXIOBASE v3.8.2"},
        {"Scope": "3.2", "Categorie": "Capital Goods", "Eenheid": "EUR", "Verbruik": "", "Emissiefactor": 0.25, "Factor eenheid": "kg CO₂e/EUR", "kg CO₂e": s3_data["cat2_capital_goods"], "Bron factor": "EXIOBASE v3.8.2"},
        {"Scope": "3.3", "Categorie": "Fuel & Energy (WTT)", "Eenheid": "n.v.t.", "Verbruik": "", "Emissiefactor": "15%/10%", "Factor eenheid": "% op S1/S2", "kg CO₂e": s3_data["cat3_fuel_energy_wtt"], "Bron factor": "co2emissiefactoren.nl"},
        {"Scope": "3.5", "Categorie": "Afval kantoor", "Eenheid": "forfaitair", "Verbruik": f"{fte_count} FTE", "Emissiefactor": FACTORS["waste_emission_factor"], "Factor eenheid": "kg CO₂e/kg afval", "kg CO₂e": s3_data["cat5_waste"], "Bron factor": "DEFRA 2024"},
        {"Scope": "3.6", "Categorie": "Zakelijke reizen", "Eenheid": "km", "Verbruik": sum(t.get("distance_km", 0) for t in travel_trips if t.get("date", "").startswith(str(current_year))), "Emissiefactor": "diverse", "Factor eenheid": "kg CO₂e/km", "kg CO₂e": s3_data["cat6_business_travel"], "Bron factor": "co2emissiefactoren.nl / DEFRA"},
        {"Scope": "3.7", "Categorie": "Woon-werkverkeer", "Eenheid": "km/jaar", "Verbruik": "", "Emissiefactor": "diverse", "Factor eenheid": "kg CO₂e/km", "kg CO₂e": s3_data["cat7_commuting"], "Bron factor": "co2emissiefactoren.nl"},
        {"Scope": "3.8", "Categorie": "Upstream Leased Assets", "Eenheid": "EUR", "Verbruik": "", "Emissiefactor": 0.10, "Factor eenheid": "kg CO₂e/EUR", "kg CO₂e": s3_data["cat8_leased_assets"], "Bron factor": "EXIOBASE v3.8.2"},
    ]
    export_df = pd.DataFrame(export_rows)

    # Add totals
    total_row = {"Scope": "TOTAAL", "Categorie": "", "Eenheid": "", "Verbruik": "", "Emissiefactor": "", "Factor eenheid": "", "kg CO₂e": total_loc, "Bron factor": ""}
    export_df = pd.concat([export_df, pd.DataFrame([total_row])], ignore_index=True)

    csv = export_df.to_csv(index=False, sep=";", decimal=",")
    st.download_button(
        "Download GHG rapport (CSV)",
        data=csv,
        file_name=f"FlexEdge_GHG_rapport_{current_year}.csv",
        mime="text/csv",
        type="primary",
    )

# ══════════════════════════════════════════════════════════════
# BENCHMARKS
# ══════════════════════════════════════════════════════════════

st.divider()
st.markdown("#### Benchmarks")

if total_loc > 0 and fte_count > 0:
    bm1, bm2, bm3 = st.columns(3)
    with bm1:
        per_fte = total_loc / fte_count
        st.metric("kg CO₂e per FTE", f"{per_fte:,.0f}")
    with bm2:
        # Revenue from Productive if available
        try:
            from services.productive_api import safe_load, get_invoices
            invoices = safe_load(get_invoices)
            year_start = f"{current_year}-01-01"
            ytd_revenue = sum(i["total_with_tax"] for i in invoices if i.get("status") == "paid" and (i.get("paid_date") or "") >= year_start)
            if ytd_revenue > 0:
                intensity = total_loc / ytd_revenue * 1000
                st.metric("kg CO₂e / EUR 1.000 omzet", f"{intensity:,.1f}")
            else:
                st.metric("kg CO₂e / EUR 1.000 omzet", "—")
        except Exception:
            st.metric("kg CO₂e / EUR 1.000 omzet", "—")
    with bm3:
        st.metric("Scope 3 aandeel", f"{(s3 / total_loc * 100):,.0f}%" if total_loc > 0 else "—",
                  help="Typisch voor dienstverlenende bedrijven: >80% Scope 3")
else:
    st.info("Voer emissiedata in om benchmarks te berekenen.")

with st.expander("Emissiefactoren & bronnen"):
    st.markdown("""
| Factor | Waarde | Eenheid | Bron |
|--------|--------|---------|------|
| Aardgas | 1.785 | kg CO₂e/m³ | co2emissiefactoren.nl 2024 |
| Elektriciteit (NL grid) | 0.328 | kg CO₂e/kWh | CBS/RVO 2024 |
| Groene stroom (GoO) | 0.000 | kg CO₂e/kWh | Market-based |
| Trein (NS) | 0.008 | kg CO₂e/km | co2emissiefactoren.nl |
| Auto (benzine) | 0.190 | kg CO₂e/km | co2emissiefactoren.nl |
| Auto (elektrisch) | 0.050 | kg CO₂e/km | co2emissiefactoren.nl |
| Vlucht (<800 km) | 0.180 | kg CO₂e/km | DEFRA 2024 |
| Vlucht (>800 km) | 0.110 | kg CO₂e/km | DEFRA 2024 |
| Kantoorafval | 0.500 | kg CO₂e/kg afval | DEFRA 2024 |
| WTT gas | +15% | op Scope 1 | co2emissiefactoren.nl |
| WTT elektra | +10% | op Scope 2 | co2emissiefactoren.nl |
    """)
