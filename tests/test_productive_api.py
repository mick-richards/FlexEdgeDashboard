"""Tests for services/productive_api.py — invoice status and helpers."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from services.productive_api import _invoice_status, build_lookup


class TestInvoiceStatus:
    def test_paid(self):
        assert _invoice_status({"paid_date": "2026-01-15"}) == "paid"

    def test_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        attrs = {"due_date": yesterday, "date": "2026-01-01"}
        assert _invoice_status(attrs) == "overdue"

    def test_sent(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        attrs = {"due_date": future, "date": "2026-01-01"}
        assert _invoice_status(attrs) == "sent"

    def test_draft(self):
        assert _invoice_status({}) == "draft"

    def test_paid_takes_precedence_over_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        attrs = {"paid_date": "2026-03-01", "due_date": yesterday}
        assert _invoice_status(attrs) == "paid"

    def test_no_due_date_with_date_is_sent(self):
        attrs = {"date": "2026-01-01"}
        assert _invoice_status(attrs) == "sent"


class TestBuildLookup:
    def test_basic(self):
        items = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]
        result = build_lookup(items)
        assert result == {"1": "Alice", "2": "Bob"}

    def test_custom_keys(self):
        items = [{"code": "NL", "label": "Netherlands"}]
        result = build_lookup(items, key="code", value="label")
        assert result == {"NL": "Netherlands"}

    def test_empty_list(self):
        assert build_lookup([]) == {}
