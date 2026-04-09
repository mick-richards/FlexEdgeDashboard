"""Actuals — werkelijke uitgaven per categorie per maand, uit banktransacties.

This service reuses the categorisation rules from the Uitgaven page but exposes them
in a pure-Python form so the cost-plan page can show "werkelijk vs begroot" variance
without duplicating logic.

Categorisation pipeline:
    1. Raw description → parent category via CATEGORY_RULES (keyword match)
    2. User overrides (data/category_overrides.json) kunnen per transactie
       een andere leaf kiezen.
    3. Aggregate: sum per (YYYY-MM, leaf) for negative transactions.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from services.bank_api import get_transactions, is_configured as bank_configured

OVERRIDES_FILE = Path(__file__).parent.parent / "data" / "category_overrides.json"

# Keyword → parent category (aligned with the centralised categories.json tree).
# Parent names MUST match a parent in data/categories.json; otherwise the mapping
# silently falls through to "Overig".
CATEGORY_RULES: dict[str, list[str]] = {
    "Salarissen": ["loonheffing", "salaris", "dga", "pensioen", "netto loon"],
    "Boekhouder": ["slingerland"],
    "Software & tools": [
        "anthropic", "claude", "github", "streamlit", "zapier", "plaud",
        "docusign", "think-cell", "microsoft 365", "norton", "cloudflare",
        "productive", "miro", "canva", "notion", "figma", "google workspace",
        "adobe", "gamma", "saas", "licentie",
    ],
    "Capital Goods": [
        "laptop", "macbook", "thinkpad", "dell ", "lenovo", "monitor",
        "ipad", "iphone", "printer", "server", "hardware", "coolblue",
        "mediamarkt", "bol.com",
    ],
    "Kantoorartikelen": [
        "papier", "inkt", "toner", "pennen", "post-it", "envelop",
        "bruna", "staples", "office depot", "hema kantoor",
        "bureau-accessoire", "ordner",
    ],
    "Kantoor": ["spaces", "swoh", "plnt", "huur"],
    "Verzekeringen": ["verzekering", "insurance", "anker"],
    "Reiskosten": [
        "ns.nl", "ov-chipkaart", "transvia", "parkeer", "shell", "bp ",
        "uber", "taxi", "booking", "hotel", "benzine", "parkeren",
    ],
    "Telecom": ["odido", "kpn", "t-mobile"],
    "Belasting": ["belastingdienst", "gemeente", "kvk", "btw", "vennootschapsbelasting"],
    "Bank": ["transactiekosten", "rente"],
    "Inhuur": ["gerben", "vermeulen", "eddie"],
    "Marketing & acquisitie": ["lunch", "restaurant", "eten", "event", "netwerk", "borrel"],
    "Opleiding": ["cursus", "course", "training", "boek", "conferentie"],
}


def _load_overrides() -> dict:
    if OVERRIDES_FILE.exists():
        return json.loads(OVERRIDES_FILE.read_text(encoding="utf-8"))
    return {}


def categorise(description: str) -> str:
    """Return the parent category for a bank-tx description, or 'Overig' if no rule matches."""
    desc = (description or "").lower()
    for parent, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            if kw in desc:
                return parent
    return "Overig"


def make_tx_key(row: dict) -> str:
    return f"{row.get('date', '')}|{row.get('amount', '')}|{str(row.get('description', ''))[:50]}"


def _ym(d: str | date) -> str:
    if isinstance(d, str):
        d = datetime.fromisoformat(d[:10]).date()
    return f"{d.year}-{d.month:02d}"


def actuals_per_month(days: int = 365) -> dict[str, dict[str, float]]:
    """Return {"YYYY-MM": {leaf: summed_outgoing_euros}}.

    Uses bank transactions of the last `days` days (default 1 year).
    Negative amounts (outgoing) are taken as positive expense values.
    Per-transaction category overrides win over keyword rules.
    """
    if not bank_configured():
        return {}

    txs = get_transactions(days=days)
    if not txs:
        return {}

    overrides = _load_overrides()
    out: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for tx in txs:
        amount = float(tx.get("amount", 0) or 0)
        if amount >= 0:
            continue  # income is not an actual cost
        leaf = overrides.get(make_tx_key(tx)) or categorise(tx.get("description", ""))
        ym = _ym(tx.get("date"))
        out[ym][leaf] += abs(amount)

    # Convert inner defaultdicts to plain dicts.
    return {ym: dict(cats) for ym, cats in out.items()}


def actuals_for_month(ym: str, days: int | None = None) -> dict[str, float]:
    """Return {leaf: total} for a specific YYYY-MM."""
    if days is None:
        # Pull enough days to cover the requested month even if it's a while back.
        y, m = map(int, ym.split("-"))
        first = date(y, m, 1)
        days = max(60, (date.today() - first).days + 31)
    per_month = actuals_per_month(days=days)
    return per_month.get(ym, {})


def income_per_month(days: int = 365) -> dict[str, float]:
    """Return {"YYYY-MM": total_incoming_euros} from bank transactions."""
    if not bank_configured():
        return {}
    txs = get_transactions(days=days)
    out: dict[str, float] = defaultdict(float)
    for tx in txs:
        amount = float(tx.get("amount", 0) or 0)
        if amount <= 0:
            continue
        ym = _ym(tx.get("date"))
        out[ym] += amount
    return dict(out)
