"""Instellingen — Bank connection and configuration."""
from __future__ import annotations

import streamlit as st

from services.bank_api import (
    is_configured as bank_configured,
    get_balance,
    find_asn_bank,
    start_authorization,
    complete_authorization,
    get_linked_account_id,
)

st.markdown("# Instellingen")

# ── Bank Connection ──
st.markdown("### Bankkoppeling (Enable Banking)")

account_id = get_linked_account_id()

if bank_configured() and account_id:
    balance = get_balance()
    if balance:
        st.success(f"Verbonden met ASN Bank. Saldo: EUR {balance['amount']:,.2f} per {balance['date']}")
    else:
        st.warning(
            "Bankkoppeling is geconfigureerd maar kan geen saldo ophalen. "
            "Mogelijk is de autorisatie verlopen (90 dagen). Koppel opnieuw hieronder."
        )

elif bank_configured():
    st.info("Enable Banking is geconfigureerd. Koppel je bankrekening hieronder.")

    # Check for callback code in URL
    query_params = st.query_params
    code = query_params.get("code")

    if code:
        st.markdown("#### Autorisatie afronden...")
        result = complete_authorization(code)
        if result:
            accounts = result.get("accounts", [])
            session_id = result.get("session_id", "")
            st.success("Bank succesvol gekoppeld!")
            st.markdown(f"**Session ID:** `{session_id}`")
            st.markdown("**Gevonden rekeningen:**")
            for acc in accounts:
                acc_id = acc.get("account_id", {})
                iban = acc_id.get("iban", "onbekend") if isinstance(acc_id, dict) else acc_id
                uid = acc.get("uid", acc_id)
                st.markdown(f"- IBAN: `{iban}` — Account ID: `{uid}`")

            st.divider()
            st.markdown("**Voeg deze waarden toe aan je Streamlit Cloud Secrets:**")
            st.code(f"""ENABLE_BANKING_ACCOUNT_ID = "{accounts[0].get('uid', '') if accounts else ''}"
ENABLE_BANKING_SESSION_ID = "{session_id}"
""", language="toml")
            st.warning("Na het toevoegen: herstart de app via Streamlit Cloud.")
            st.query_params.clear()
        else:
            st.error("Kon de autorisatie niet afronden. Probeer opnieuw.")
    else:
        st.markdown("#### Stap 1: Bank zoeken")
        if st.button("Zoek ASN Bank", type="secondary"):
            bank_name = find_asn_bank()
            if bank_name:
                st.session_state["_eb_bank_name"] = bank_name
                st.success(f"Gevonden: **{bank_name}**")
            else:
                st.error("ASN Bank niet gevonden. Controleer je API credentials.")

        bank_name = st.session_state.get("_eb_bank_name")
        if not bank_name:
            bank_name = st.text_input(
                "Bank naam (als automatisch zoeken niet werkt)",
                value="ASN Bank",
                key="manual_bank_name",
            )

        st.markdown("#### Stap 2: Autoriseren")
        if st.button("Koppel bankrekening", type="primary"):
            auth = start_authorization(bank_name)
            if auth:
                url = auth["url"]
                st.markdown(f"**Klik op de link hieronder om je bank te autoriseren:**")
                st.markdown(f"[Ga naar ASN Bank autorisatie]({url})")
                st.info(
                    "Na het inloggen bij je bank word je teruggestuurd naar deze app. "
                    "De koppeling wordt dan automatisch afgerond."
                )
            else:
                st.error("Kon geen autorisatie starten. Controleer je credentials en probeer opnieuw.")

else:
    st.markdown("""
    De bankkoppeling is nog niet ingesteld. Voeg deze waarden toe aan **Streamlit Cloud Secrets**:
    """)

    st.code("""
# Enable Banking
ENABLE_BANKING_APP_ID = "jouw-app-id"
ENABLE_BANKING_PRIVATE_KEY = \"\"\"-----BEGIN PRIVATE KEY-----
... (plak hier de volledige inhoud van je .pem bestand) ...
-----END PRIVATE KEY-----\"\"\"
    """, language="toml")

    st.markdown("Na het toevoegen: herstart de app en kom terug naar deze pagina om je bank te koppelen.")

st.divider()

# ── Productive Connection ──
st.markdown("### Productive.io")
try:
    token = st.secrets["PRODUCTIVE_API_TOKEN"]
    org_id = st.secrets["PRODUCTIVE_ORG_ID"]
    st.success(f"Verbonden (org: {org_id})")
except Exception:
    st.error("Productive API credentials niet gevonden in secrets.")

st.divider()

st.markdown("### Over")
st.markdown("""
**FlexEdge Dashboard** v0.2

Data bronnen: Productive.io (facturen, uren, pipeline) + Enable Banking (banksaldo, transacties via PSD2).
Bankautorisatie verloopt na 90 dagen.

*FlexEdge B.V. — 2026*
""")
