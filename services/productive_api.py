"""Productive.io API client for the FlexEdge Dashboard.

Fetches invoices, time entries, deals, budgets, and tasks from Productive.
API credentials are read from Streamlit secrets or environment variables.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests
import streamlit as st

BASE_URL = "https://api.productive.io/api/v2"


def _get_credentials() -> tuple[str, str]:
    """Return (api_token, org_id) from secrets or env."""
    try:
        token = st.secrets["PRODUCTIVE_API_TOKEN"]
        org_id = st.secrets["PRODUCTIVE_ORG_ID"]
    except Exception:
        token = os.environ.get("PRODUCTIVE_API_TOKEN", "")
        org_id = os.environ.get("PRODUCTIVE_ORG_ID", "")
    return token, org_id


def _headers() -> dict[str, str]:
    token, org_id = _get_credentials()
    return {
        "Content-Type": "application/vnd.api+json",
        "X-Auth-Token": token,
        "X-Organization-Id": org_id,
    }


def _get(endpoint: str, params: dict | None = None) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params or {}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _get_all_pages(endpoint: str, params: dict | None = None, max_pages: int = 10) -> list[dict]:
    params = dict(params or {})
    params.setdefault("page[size]", "200")
    all_data = []
    for page_num in range(1, max_pages + 1):
        params["page[number]"] = str(page_num)
        result = _get(endpoint, params)
        data = result.get("data", [])
        all_data.extend(data)
        meta = result.get("meta", {})
        total_pages = meta.get("total_pages", 1)
        if page_num >= total_pages:
            break
    return all_data


# ── Invoices ──

@st.cache_data(ttl=300)
def get_invoices() -> list[dict]:
    raw = _get_all_pages("invoices", {"page[size]": "200"})
    invoices = []
    for item in raw:
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        inv = {
            "id": item["id"],
            "number": attrs.get("number", ""),
            "date": attrs.get("date"),
            "due_date": attrs.get("due_date"),
            "paid_date": attrs.get("paid_date"),
            "total": float(attrs.get("total", 0) or 0),
            "total_with_tax": float(attrs.get("total_with_tax", 0) or 0),
            "currency": attrs.get("currency", "EUR"),
            "status": _invoice_status(attrs),
            "company_id": rels.get("company", {}).get("data", {}).get("id"),
        }
        invoices.append(inv)
    return invoices


def _invoice_status(attrs: dict) -> str:
    if attrs.get("paid_date"):
        return "paid"
    due = attrs.get("due_date")
    if due and due < date.today().isoformat():
        return "overdue"
    if attrs.get("date"):
        return "sent"
    return "draft"


# ── Time Entries ──

@st.cache_data(ttl=300)
def get_time_entries(after: str | None = None, before: str | None = None) -> list[dict]:
    params: dict[str, Any] = {"page[size]": "200"}
    if after:
        params["filter[after]"] = after
    if before:
        params["filter[before]"] = before
    raw = _get_all_pages("time_entries", params)
    entries = []
    for item in raw:
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        entries.append({
            "id": item["id"],
            "date": attrs.get("date"),
            "minutes": int(attrs.get("time", 0) or 0),
            "note": attrs.get("note", ""),
            "billable": attrs.get("billable", False),
            "person_id": rels.get("person", {}).get("data", {}).get("id"),
            "service_id": rels.get("service", {}).get("data", {}).get("id"),
            "project_id": rels.get("project", {}).get("data", {}).get("id"),
        })
    return entries


# ── Deals ──

@st.cache_data(ttl=300)
def get_deals() -> list[dict]:
    # Productive uses deals endpoint with filter[type]=1 for sales deals
    raw = _get_all_pages("deals", {"page[size]": "200", "filter[type]": "1"})
    deals = []
    for item in raw:
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        revenue = float(attrs.get("budget_total", 0) or 0)
        prob = int(attrs.get("probability", 50) or 50)
        sales_status = attrs.get("sales_status_title", "")
        closed = attrs.get("closed_at")
        deals.append({
            "id": item["id"],
            "name": attrs.get("name", ""),
            "number": attrs.get("number"),
            "revenue": revenue,
            "probability": prob,
            "status": sales_status,
            "weighted_value": revenue * prob / 100,
            "company_id": rels.get("company", {}).get("data", {}).get("id"),
            "date": attrs.get("date"),
            "closed": bool(closed),
        })
    return deals


# ── Budgets (stored as deals with type=2 in Productive) ──

@st.cache_data(ttl=300)
def get_budgets() -> list[dict]:
    raw = _get_all_pages("deals", {"page[size]": "200", "filter[type]": "2"})
    budgets = []
    for item in raw:
        attrs = item.get("attributes", {})
        rels = item.get("relationships", {})
        total_time = float(attrs.get("total_time", 0) or 0)
        worked_time = float(attrs.get("worked_time", 0) or 0)
        budgets.append({
            "id": item["id"],
            "name": attrs.get("name", ""),
            "budget_type": attrs.get("budget_type"),
            "revenue": float(attrs.get("revenue", 0) or 0),
            "cost": float(attrs.get("cost", 0) or 0),
            "profit": float(attrs.get("profit", 0) or 0),
            "total_hours": total_time / 60,
            "spent_hours": worked_time / 60,
            "remaining_hours": (total_time - worked_time) / 60,
            "project_id": rels.get("project", {}).get("data", {}).get("id"),
        })
    return budgets


# ── People ──

@st.cache_data(ttl=600)
def get_people() -> list[dict]:
    raw = _get_all_pages("people", {"page[size]": "200"})
    return [
        {
            "id": item["id"],
            "name": f"{item['attributes'].get('first_name', '')} {item['attributes'].get('last_name', '')}".strip(),
            "email": item["attributes"].get("email", ""),
        }
        for item in raw
    ]


# ── Projects ──

@st.cache_data(ttl=600)
def get_projects() -> list[dict]:
    raw = _get_all_pages("projects", {"page[size]": "200"})
    return [
        {
            "id": item["id"],
            "name": item["attributes"].get("name", ""),
        }
        for item in raw
    ]


# ── Companies ──

@st.cache_data(ttl=600)
def get_companies() -> list[dict]:
    raw = _get_all_pages("companies", {"page[size]": "200"})
    return [
        {
            "id": item["id"],
            "name": item["attributes"].get("name", ""),
        }
        for item in raw
    ]


def build_lookup(items: list[dict], key: str = "id", value: str = "name") -> dict:
    return {item[key]: item[value] for item in items}
