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
def _get_users() -> dict:
    """Load per-user credentials from secrets. Returns {username: {password, role, holding}}."""
    try:
        users_section = st.secrets.get("users", {})
        if users_section and hasattr(users_section, "keys"):
            return {k: dict(v) if hasattr(v, "keys") else {"password": v} for k, v in users_section.items()}
    except Exception:
        pass
    return {}


def _check_auth() -> bool:
    if st.session_state.get("authenticated"):
        return True

    users = _get_users()

    # Fallback: legacy single-password auth
    try:
        auth_password = st.secrets.get("AUTH_PASSWORD", "")
        if not auth_password:
            auth_section = st.secrets.get("auth", {})
            auth_password = auth_section.get("password", "") if isinstance(auth_section, dict) else ""
    except Exception:
        auth_password = ""

    if not users and not auth_password:
        return True

    col_l, col_c, col_r = st.columns([1, 1.2, 1])
    with col_c:
        st.markdown('<div style="height: 12vh;"></div>', unsafe_allow_html=True)
        st.markdown("## FlexEdge Dashboard")
        with st.form("auth_form"):
            if users:
                username = st.text_input("Gebruiker", placeholder="Gebruikersnaam")
            password = st.text_input("Wachtwoord", type="password", placeholder="Wachtwoord")
            submitted = st.form_submit_button("Inloggen", type="primary", use_container_width=True)
            if submitted:
                if users:
                    user_key = username.lower().strip()
                    user = users.get(user_key)
                    if user and password == user.get("password", ""):
                        st.session_state["authenticated"] = True
                        st.session_state["user"] = user_key
                        st.session_state["user_role"] = user.get("role", "user")
                        st.session_state["user_holding"] = user.get("holding", "")
                        st.rerun()
                    elif password == auth_password and auth_password:
                        # Fallback to shared password (no user context)
                        st.session_state["authenticated"] = True
                        st.rerun()
                    else:
                        st.error("Onjuiste gebruikersnaam of wachtwoord")
                elif password == auth_password:
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
maandreview = st.Page("pages/0b_Maandreview.py", title="Maandreview", icon=":material/calendar_month:")
runway = st.Page("pages/1_Runway.py", title="Runway", icon=":material/savings:")
expenses = st.Page("pages/2_Uitgaven.py", title="Uitgaven", icon=":material/payments:")
cost_plan = st.Page("pages/3_Kostenplan.py", title="Kostenplan", icon=":material/edit_calendar:")
revenue = st.Page("pages/4_Omzet.py", title="Omzet & Facturen", icon=":material/receipt_long:")
pipeline = st.Page("pages/5_Pipeline.py", title="Pipeline", icon=":material/filter_alt:")
utilization = st.Page("pages/6_Uren.py", title="Uren & Bezetting", icon=":material/schedule:")
resourcing = st.Page("pages/7_Resourcing.py", title="Resourcing", icon=":material/groups:")
emissions = st.Page("pages/9_Emissies.py", title="Emissies", icon=":material/eco:")
holding = st.Page("pages/10_Holding.py", title="Mijn Holding", icon=":material/account_balance:")
settings = st.Page("pages/8_Instellingen.py", title="Instellingen", icon=":material/settings:")

nav_sections = {
    "Overzicht": [weekstart, maandreview],
    "Financieel": [runway, expenses, cost_plan, revenue],
    "Sales": [pipeline],
    "Team": [utilization, resourcing],
    "Duurzaamheid": [emissions],
    "Systeem": [settings],
}
# Only show Holding page if user is logged in with a user account
if st.session_state.get("user_holding"):
    nav_sections["Holding"] = [holding]

pg = st.navigation(nav_sections)

# Sidebar header
with st.sidebar:
    st.markdown(
        '<p style="font-size:1.15rem; font-weight:700; color:#1D1D1F; '
        'margin:0 0 2px 0; letter-spacing:-0.02em;">FlexEdge</p>'
        '<p style="font-size:0.78rem; color:#86868B; margin:0 0 8px 0;">'
        'Financial Dashboard</p>',
        unsafe_allow_html=True,
    )
    if st.session_state.get("user"):
        user = st.session_state["user"].capitalize()
        holding = st.session_state.get("user_holding", "")
        st.caption(f"Ingelogd als **{user}**" + (f" ({holding})" if holding else ""))
        if st.button("Uitloggen", key="logout", type="tertiary"):
            for key in ["authenticated", "user", "user_role", "user_holding"]:
                st.session_state.pop(key, None)
            st.rerun()
    st.divider()

pg.run()
