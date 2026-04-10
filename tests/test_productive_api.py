"""Tests for services/productive_api.py — invoice status logic and helpers."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.productive_api import _invoice_status, build_lookup


# ── _invoice_status ──

class TestInvoiceStatus:
    def test_paid(self):
        attrs = {"paid_date": "2026-01-15", "date": "2026-01-01", "due_date": "2026-01-10"}
        assert _invoice_status(attrs) == "paid"

    def test_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        attrs = {"date": "2026-01-01", "due_date": yesterday}
        assert _invoice_status(attrs) == "overdue"

    def test_sent(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        attrs = {"date": "2026-01-01", "due_date": tomorrow}
        assert _invoice_status(attrs) == "sent"

    def test_draft(self):
        attrs = {}
        assert _invoice_status(attrs) == "draft"

    def test_sent_no_due_date(self):
        attrs = {"date": "2026-01-01"}
        assert _invoice_status(attrs) == "sent"

    def test_paid_overrides_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        attrs = {"paid_date": "2026-02-01", "due_date": yesterday, "date": "2026-01-01"}
        assert _invoice_status(attrs) == "paid"


# ── build_lookup ──

class TestBuildLookup:
    def test_basic(self):
        items = [
            {"id": "1", "name": "Alpha"},
            {"id": "2", "name": "Beta"},
        ]
        assert build_lookup(items) == {"1": "Alpha", "2": "Beta"}

    def test_custom_keys(self):
        items = [{"code": "NL", "label": "Netherlands"}]
        assert build_lookup(items, key="code", value="label") == {"NL": "Netherlands"}

    def test_empty(self):
        assert build_lookup([]) == {}
