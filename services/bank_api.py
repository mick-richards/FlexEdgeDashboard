"""Enable Banking API client.

Connects to ASN Bank (de Volksbank) via PSD2 Open Banking to fetch
account balances and transactions.

Uses JWT (RS256) authentication with an RSA private key.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import jwt
import requests
import streamlit as st

BASE_URL = "https://api.enablebanking.com"

# Path to private key (local dev)
_KEY_PATH = Path(__file__).parent.parent / ".streamlit" / "enable_banking_key.pem"


def _get_app_id() -> str:
    try:
        val = st.secrets.get("ENABLE_BANKING_APP_ID")
        if val:
            return str(val)
    except Exception:
        pass
    try:
        return st.secrets["ENABLE_BANKING_APP_ID"]
    except Exception:
        pass
    return os.environ.get("ENABLE_BANKING_APP_ID", "")


def _get_private_key() -> str:
    import base64
    # Try split base64 key parts (EB_KEY_1 through EB_KEY_5)
    try:
        parts = []
        for i in range(1, 20):
            part = st.secrets.get(f"EB_KEY_{i}", "")
            if part:
                parts.append(str(part))
        if parts:
            combined = "".join(parts)
            return base64.b64decode(combined).decode("utf-8")
    except Exception:
        pass
    # Try single base64-encoded key
    try:
        val = st.secrets.get("ENABLE_BANKING_PRIVATE_KEY_B64", "")
        if val:
            return base64.b64decode(str(val)).decode("utf-8")
    except Exception:
        pass
    # Try plain key from secrets
    try:
        val = st.secrets.get("ENABLE_BANKING_PRIVATE_KEY", "")
        if val:
            return str(val)
    except Exception:
        pass
    # Fall back to local .pem file
    if _KEY_PATH.exists():
        return _KEY_PATH.read_text(encoding="utf-8")
    return ""


def _make_jwt() -> str:
    app_id = _get_app_id()
    private_key = _get_private_key()
    now = int(time.time())
    payload = {
        "iss": "enablebanking.com",
        "aud": "api.enablebanking.com",
        "iat": now,
        "exp": now + 3600,
    }
    return jwt.encode(
        payload, private_key, algorithm="RS256",
        headers={"kid": app_id},
    )


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_make_jwt()}",
        "Content-Type": "application/json",
    }


def is_configured() -> bool:
    return bool(_get_app_id() and _get_private_key())


def get_linked_account_id() -> str:
    try:
        return st.secrets.get("ENABLE_BANKING_ACCOUNT_ID", "")
    except Exception:
        return os.environ.get("ENABLE_BANKING_ACCOUNT_ID", "")


def get_session_id() -> str:
    try:
        return st.secrets.get("ENABLE_BANKING_SESSION_ID", "")
    except Exception:
        return os.environ.get("ENABLE_BANKING_SESSION_ID", "")


def get_redirect_url() -> str:
    try:
        return st.secrets.get("ENABLE_BANKING_REDIRECT_URL",
                              "https://flexedgedashboard-6dhywecpats36vavl2xexe.streamlit.app/")
    except Exception:
        return "https://flexedgedashboard-6dhywecpats36vavl2xexe.streamlit.app/"


# ── Bank Discovery ──

def list_banks(country: str = "NL") -> list[dict]:
    """List available banks for a country."""
    try:
        resp = requests.get(
            f"{BASE_URL}/aspsps",
            params={"country": country},
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json().get("aspsps", [])
    except Exception:
        pass
    return []


def find_asn_bank() -> str | None:
    """Find the exact ASN Bank name in Enable Banking."""
    banks = list_banks("NL")
    for bank in banks:
        name = bank.get("name", "").lower()
        if "asn" in name or "volksbank" in name:
            return bank["name"]
    return None


# ── Authorization Flow ──

def start_authorization(aspsp_name: str = "ASN Bank") -> dict | None:
    """Start bank authorization. Returns dict with 'url' and 'authorization_id'."""
    import uuid
    state = str(uuid.uuid4())
    st.session_state["_eb_auth_state"] = state

    # Consent valid for 90 days
    valid_until = (date.today() + timedelta(days=89)).isoformat() + "T00:00:00.000000+00:00"

    try:
        resp = requests.post(
            f"{BASE_URL}/auth",
            json={
                "access": {
                    "valid_until": valid_until,
                    "balances": True,
                    "transactions": True,
                },
                "aspsp": {
                    "name": aspsp_name,
                    "country": "NL",
                },
                "state": state,
                "redirect_url": get_redirect_url(),
                "psu_type": "business",
            },
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            st.session_state["_eb_auth_id"] = data.get("authorization_id")
            return {
                "url": data["url"],
                "authorization_id": data.get("authorization_id"),
            }
    except Exception as e:
        st.error(f"Authorization error: {e}")
    return None


def complete_authorization(code: str) -> dict | None:
    """Exchange authorization code for a session with account IDs."""
    try:
        resp = requests.post(
            f"{BASE_URL}/sessions",
            json={"code": code},
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code in (200, 201):
            session = resp.json()
            return {
                "session_id": session.get("session_id"),
                "accounts": session.get("accounts", []),
            }
    except Exception as e:
        st.error(f"Session error: {e}")
    return None


# ── Per-account helpers (for holding accounts) ──

def _load_holding_bank_config(user: str) -> dict:
    """Load bank config for a holding user from data/holding_{user}_bank.json."""
    import json
    path = Path(__file__).parent.parent / "data" / f"holding_{user}_bank.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_holding_bank_config(user: str, config: dict) -> None:
    """Save bank config for a holding user."""
    import json
    path = Path(__file__).parent.parent / "data" / f"holding_{user}_bank.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")


def get_balance_for_account(account_id: str) -> dict | None:
    """Fetch balance for a specific account ID (uses shared EB credentials)."""
    if not account_id or not is_configured():
        return None
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/balances",
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        balances = resp.json().get("balances", [])
        preferred_types = ["CLAV", "XPCD", "ITAV", "CLBD", "ITBD"]
        for ptype in preferred_types:
            for bal in balances:
                if bal.get("balance_type") == ptype:
                    return {
                        "amount": float(bal["balance_amount"]["amount"]),
                        "currency": bal["balance_amount"]["currency"],
                        "date": bal.get("reference_date", date.today().isoformat()),
                    }
        if balances:
            bal = balances[0]
            return {
                "amount": float(bal["balance_amount"]["amount"]),
                "currency": bal["balance_amount"]["currency"],
                "date": bal.get("reference_date", date.today().isoformat()),
            }
    except Exception:
        pass
    return None


def get_transactions_for_account(account_id: str, days: int = 90) -> list[dict]:
    """Fetch transactions for a specific account ID."""
    if not account_id or not is_configured():
        return []

    date_from = (date.today() - timedelta(days=days)).isoformat()
    date_to = date.today().isoformat()
    all_transactions = []

    try:
        continuation_key = None
        for _ in range(10):
            params = {"date_from": date_from, "date_to": date_to}
            if continuation_key:
                params["continuation_key"] = continuation_key
            resp = requests.get(
                f"{BASE_URL}/accounts/{account_id}/transactions",
                headers=_headers(),
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for tx in data.get("transactions", []):
                amount = tx.get("transaction_amount", {})
                indicator = tx.get("credit_debit_indicator", "")
                raw_amount = float(amount.get("amount", 0))
                if indicator == "DBIT":
                    raw_amount = -abs(raw_amount)
                remittance = tx.get("remittance_information", [])
                description = remittance[0] if remittance else ""
                creditor = tx.get("creditor", {}).get("name", "") if isinstance(tx.get("creditor"), dict) else ""
                debtor = tx.get("debtor", {}).get("name", "") if isinstance(tx.get("debtor"), dict) else ""
                all_transactions.append({
                    "date": tx.get("booking_date", ""),
                    "amount": raw_amount,
                    "currency": amount.get("currency", "EUR"),
                    "description": description or creditor or debtor,
                    "creditor": creditor,
                    "debtor": debtor,
                    "type": "incoming" if indicator == "CRDT" else "outgoing",
                })
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break
    except Exception:
        pass

    return sorted(all_transactions, key=lambda x: x["date"], reverse=True)


# ── Data Retrieval (FlexEdge BV — default account) ──

@st.cache_data(ttl=900)
def get_balance() -> dict | None:
    """Fetch current account balance."""
    account_id = get_linked_account_id()
    if not account_id or not is_configured():
        return None
    try:
        resp = requests.get(
            f"{BASE_URL}/accounts/{account_id}/balances",
            headers=_headers(),
            timeout=30,
        )
        if resp.status_code != 200:
            return None
        balances = resp.json().get("balances", [])
        # Prefer closing available or expected balance
        preferred_types = ["CLAV", "XPCD", "ITAV", "CLBD", "ITBD"]
        for ptype in preferred_types:
            for bal in balances:
                if bal.get("balance_type") == ptype:
                    return {
                        "amount": float(bal["balance_amount"]["amount"]),
                        "currency": bal["balance_amount"]["currency"],
                        "date": bal.get("reference_date", date.today().isoformat()),
                    }
        # Fallback to first available
        if balances:
            bal = balances[0]
            return {
                "amount": float(bal["balance_amount"]["amount"]),
                "currency": bal["balance_amount"]["currency"],
                "date": bal.get("reference_date", date.today().isoformat()),
            }
    except Exception:
        pass
    return None


@st.cache_data(ttl=900)
def get_transactions(days: int = 90) -> list[dict]:
    """Fetch recent transactions."""
    account_id = get_linked_account_id()
    if not account_id or not is_configured():
        return []

    date_from = (date.today() - timedelta(days=days)).isoformat()
    date_to = date.today().isoformat()

    all_transactions = []
    continuation_key = None

    try:
        for _ in range(10):  # max 10 pages
            params = {"date_from": date_from, "date_to": date_to}
            if continuation_key:
                params["continuation_key"] = continuation_key

            resp = requests.get(
                f"{BASE_URL}/accounts/{account_id}/transactions",
                headers=_headers(),
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                break

            data = resp.json()
            for tx in data.get("transactions", []):
                amount = tx.get("transaction_amount", {})
                indicator = tx.get("credit_debit_indicator", "")
                raw_amount = float(amount.get("amount", 0))
                # Make outgoing negative
                if indicator == "DBIT":
                    raw_amount = -abs(raw_amount)

                remittance = tx.get("remittance_information", [])
                description = remittance[0] if remittance else ""
                creditor = tx.get("creditor", {}).get("name", "") if isinstance(tx.get("creditor"), dict) else ""
                debtor = tx.get("debtor", {}).get("name", "") if isinstance(tx.get("debtor"), dict) else ""

                all_transactions.append({
                    "date": tx.get("booking_date", ""),
                    "amount": raw_amount,
                    "currency": amount.get("currency", "EUR"),
                    "description": description or creditor or debtor,
                    "creditor": creditor,
                    "debtor": debtor,
                    "type": "incoming" if indicator == "CRDT" else "outgoing",
                })

            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break

    except Exception:
        pass

    return sorted(all_transactions, key=lambda x: x["date"], reverse=True)
