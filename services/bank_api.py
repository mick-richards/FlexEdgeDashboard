"""GoCardless Bank Account Data API (formerly Nordigen) client.

Connects to ASN Bank (de Volksbank) via PSD2 Open Banking to fetch
account balances and transactions.

Setup:
1. Create free account at https://bankaccountdata.gocardless.com
2. Generate secret_id and secret_key
3. Add to Streamlit secrets: GOCARDLESS_SECRET_ID, GOCARDLESS_SECRET_KEY
4. Run authorize_bank() once to link your ASN Bank account
5. Add GOCARDLESS_ACCOUNT_ID to secrets after authorization
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta

import requests
import streamlit as st

BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"


def _get_credentials() -> tuple[str, str]:
    try:
        secret_id = st.secrets["GOCARDLESS_SECRET_ID"]
        secret_key = st.secrets["GOCARDLESS_SECRET_KEY"]
    except Exception:
        secret_id = os.environ.get("GOCARDLESS_SECRET_ID", "")
        secret_key = os.environ.get("GOCARDLESS_SECRET_KEY", "")
    return secret_id, secret_key


def _get_access_token() -> str | None:
    cached = st.session_state.get("_gc_token")
    expires = st.session_state.get("_gc_token_expires", 0)
    if cached and datetime.now().timestamp() < expires:
        return cached

    secret_id, secret_key = _get_credentials()
    if not secret_id or not secret_key:
        return None

    resp = requests.post(
        f"{BASE_URL}/token/new/",
        json={"secret_id": secret_id, "secret_key": secret_key},
        timeout=30,
    )
    if resp.status_code != 200:
        return None

    data = resp.json()
    token = data.get("access")
    expires_in = data.get("access_expires", 86400)
    st.session_state["_gc_token"] = token
    st.session_state["_gc_token_expires"] = datetime.now().timestamp() + expires_in - 60
    return token


def _headers() -> dict[str, str]:
    token = _get_access_token()
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    secret_id, secret_key = _get_credentials()
    return bool(secret_id and secret_key)


def get_linked_account_id() -> str | None:
    try:
        return st.secrets.get("GOCARDLESS_ACCOUNT_ID", "")
    except Exception:
        return os.environ.get("GOCARDLESS_ACCOUNT_ID", "")


@st.cache_data(ttl=900)
def get_balance() -> dict | None:
    account_id = get_linked_account_id()
    if not account_id or not is_configured():
        return None
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/balances/",
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        balances = resp.json().get("balances", [])
        for bal in balances:
            if bal.get("balanceType") == "expected":
                return {
                    "amount": float(bal["balanceAmount"]["amount"]),
                    "currency": bal["balanceAmount"]["currency"],
                    "date": bal.get("referenceDate", date.today().isoformat()),
                }
        if balances:
            bal = balances[0]
            return {
                "amount": float(bal["balanceAmount"]["amount"]),
                "currency": bal["balanceAmount"]["currency"],
                "date": bal.get("referenceDate", date.today().isoformat()),
            }
    except Exception:
        pass
    return None


@st.cache_data(ttl=900)
def get_transactions(days: int = 90) -> list[dict]:
    account_id = get_linked_account_id()
    if not account_id or not is_configured():
        return []
    date_from = (date.today() - timedelta(days=days)).isoformat()
    date_to = date.today().isoformat()
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/transactions/",
            headers=_headers(),
            params={"date_from": date_from, "date_to": date_to},
            timeout=30,
        )
        if resp.status_code != 200:
            return []
        booked = resp.json().get("transactions", {}).get("booked", [])
        return sorted(
            [
                {
                    "date": tx.get("bookingDate", ""),
                    "amount": float(tx.get("transactionAmount", {}).get("amount", 0)),
                    "currency": tx.get("transactionAmount", {}).get("currency", "EUR"),
                    "description": tx.get("remittanceInformationUnstructured", "")
                    or tx.get("creditorName", "")
                    or tx.get("debtorName", ""),
                }
                for tx in booked
            ],
            key=lambda x: x["date"],
            reverse=True,
        )
    except Exception:
        return []
