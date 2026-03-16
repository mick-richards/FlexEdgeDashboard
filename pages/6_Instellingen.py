"""Instellingen — Bank connection and configuration."""
from __future__ import annotations

import streamlit as st

from services.bank_api import is_configured as bank_configured, get_balance

st.markdown("# Instellingen")

# ── Bank Connection ──
st.markdown("### Bankkoppeling (GoCardless)")

if bank_configured():
    balance = get_balance()
    if balance:
        st.success(f"Verbonden met bankrekening. Saldo: EUR {balance['amount']:,.2f} per {balance['date']}")
    else:
        st.warning(
            "GoCardless is geconfigureerd maar kan geen saldo ophalen. "
            "Mogelijk is de bank-autorisatie verlopen (90 dagen PSD2)."
        )
else:
    st.markdown("""
    De bankkoppeling is nog niet ingesteld. Volg deze stappen:

    **1. GoCardless account aanmaken**
    - Ga naar [bankaccountdata.gocardless.com](https://bankaccountdata.gocardless.com)
    - Maak een gratis account aan (geen creditcard nodig)

    **2. API credentials genereren**
    - In het GoCardless dashboard: ga naar **User secrets**
    - Maak een nieuw secret aan — je krijgt een `secret_id` en `secret_key`

    **3. Toevoegen aan Streamlit secrets**
    """)

    st.code("""
# In .streamlit/secrets.toml of Streamlit Cloud Secrets:
GOCARDLESS_SECRET_ID = "jouw_secret_id"
GOCARDLESS_SECRET_KEY = "jouw_secret_key"
    """, language="toml")

    st.markdown("""
    **4. Bank autoriseren**
    - Na het toevoegen van de credentials, verschijnt hier een knop om je ASN Bank te koppelen
    - Je wordt doorgestuurd naar je bank om toestemming te geven (read-only)
    - Na autorisatie: voeg het `GOCARDLESS_ACCOUNT_ID` toe aan secrets

    **5. Verlengen**
    - PSD2 autorisatie verloopt na **90 dagen** — dan opnieuw koppelen
    - De app waarschuwt je wanneer dit nodig is
    """)

st.divider()

# ── Productive Connection ──
st.markdown("### Productive.io")
try:
    token = st.secrets["PRODUCTIVE_API_TOKEN"]
    org_id = st.secrets["PRODUCTIVE_ORG_ID"]
    st.success(f"Verbonden (org: {org_id})")
except Exception:
    st.error("Productive API credentials niet gevonden. Voeg PRODUCTIVE_API_TOKEN en PRODUCTIVE_ORG_ID toe aan secrets.")

st.divider()

# ── About ──
st.markdown("### Over")
st.markdown("""
**FlexEdge Dashboard** v0.1

Gebouwd voor de wekelijkse weekstart met Mick & Joris.
Data bronnen: Productive.io (facturen, uren, pipeline) + GoCardless (banksaldo).

*FlexEdge B.V. — 2026*
""")
