"""FlexEdge Dashboard — Financial overview for Mick & Joris.

Standalone Streamlit app for runway, revenue, pipeline, utilization,
and resourcing. Connects to Productive.io and GoCardless (bank).
"""
from __future__ import annotations

import streamlit as st

st.set_page_config(
    page_title="FlexEdge Dashboard",
    page_icon=":material/monitoring:",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Auth ──
def _check_auth() -> bool:
    try:
        # Support both flat (AUTH_PASSWORD) and nested ([auth].password)
        auth_password = st.secrets.get("AUTH_PASSWORD", "")
        if not auth_password:
            auth_section = st.secrets.get("auth", {})
            auth_password = auth_section.get("password", "") if isinstance(auth_section, dict) else ""
    except Exception:
        return True
    if not auth_password:
        return True
    if st.session_state.get("authenticated"):
        return True

    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        st.markdown('<div style="height: 12vh;"></div>', unsafe_allow_html=True)
        st.markdown("## FlexEdge Dashboard")
        with st.form("auth_form"):
            password = st.text_input("Wachtwoord", type="password", placeholder="Wachtwoord")
            submitted = st.form_submit_button("Inloggen", type="primary", use_container_width=True)
            if submitted:
                if password == auth_password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Onjuist wachtwoord")
    return False


if not _check_auth():
    st.stop()

# ── Handle bank callback before page routing ──
_bank_code = st.query_params.get("code")
if _bank_code and "bank_callback_handled" not in st.session_state:
    from services.bank_api import complete_authorization, is_configured
    if is_configured():
        result = complete_authorization(_bank_code)
        if result:
            st.session_state["bank_callback_handled"] = True
            st.session_state["bank_callback_result"] = result
            st.query_params.clear()

# ── Navigation ──
weekstart = st.Page("pages/0_Weekstart.py", title="Weekstart", icon=":material/dashboard:", default=True)
runway = st.Page("pages/1_Runway.py", title="Runway", icon=":material/savings:")
expenses = st.Page("pages/2_Uitgaven.py", title="Uitgaven", icon=":material/payments:")
cost_plan = st.Page("pages/3_Kostenplan.py", title="Kostenplan", icon=":material/edit_calendar:")
revenue = st.Page("pages/4_Omzet.py", title="Omzet & Facturen", icon=":material/receipt_long:")
pipeline = st.Page("pages/5_Pipeline.py", title="Pipeline", icon=":material/filter_alt:")
utilization = st.Page("pages/6_Uren.py", title="Uren & Bezetting", icon=":material/schedule:")
resourcing = st.Page("pages/7_Resourcing.py", title="Resourcing", icon=":material/groups:")
settings = st.Page("pages/8_Instellingen.py", title="Instellingen", icon=":material/settings:")

pg = st.navigation({
    "Overzicht": [weekstart],
    "Financieel": [runway, expenses, cost_plan, revenue, pipeline],
    "Team": [utilization, resourcing],
    "Systeem": [settings],
})

# Sidebar header
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.15rem; font-weight:700; color:#1D1D1F; '
        'margin:0 0 2px 0; letter-spacing:-0.02em;">FlexEdge</p>'
        '<p style="font-size:0.78rem; color:#86868B; margin:0 0 8px 0;">'
        'Financial Dashboard</p>',
        unsafe_allow_html=True,
    )
    st.divider()

pg.run()
