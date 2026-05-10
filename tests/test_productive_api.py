"""Tests for services/productive_api.py — Productive.io API client."""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.productive_api import (
    _invoice_status,
    build_lookup,
    _get_all_pages,
    _safe_fetch,
    _ApiError,
    safe_load,
)


# ── Invoice status logic ──

class TestInvoiceStatus:
    def test_paid(self):
        assert _invoice_status({"paid_date": "2026-01-15"}) == "paid"

    def test_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        assert _invoice_status({"due_date": yesterday, "date": "2026-01-01"}) == "overdue"

    def test_sent(self):
        future = (date.today() + timedelta(days=30)).isoformat()
        assert _invoice_status({"due_date": future, "date": "2026-01-01"}) == "sent"

    def test_sent_no_due_date(self):
        assert _invoice_status({"date": "2026-01-01"}) == "sent"

    def test_draft(self):
        assert _invoice_status({}) == "draft"

    def test_paid_takes_precedence_over_overdue(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        attrs = {"paid_date": "2026-01-20", "due_date": yesterday, "date": "2026-01-01"}
        assert _invoice_status(attrs) == "paid"


# ── build_lookup ──

class TestBuildLookup:
    def test_default_keys(self):
        items = [
            {"id": "1", "name": "Alice"},
            {"id": "2", "name": "Bob"},
        ]
        assert build_lookup(items) == {"1": "Alice", "2": "Bob"}

    def test_custom_keys(self):
        items = [{"code": "NL", "label": "Netherlands"}]
        assert build_lookup(items, key="code", value="label") == {"NL": "Netherlands"}

    def test_empty_list(self):
        assert build_lookup([]) == {}


# ── Pagination ──

class TestGetAllPages:
    @patch("services.productive_api._get")
    def test_single_page(self, mock_get):
        mock_get.return_value = {
            "data": [{"id": "1"}, {"id": "2"}],
            "meta": {"total_pages": 1},
        }
        result = _get_all_pages("invoices")
        assert len(result) == 2
        mock_get.assert_called_once()

    @patch("services.productive_api._get")
    def test_multiple_pages(self, mock_get):
        mock_get.side_effect = [
            {"data": [{"id": "1"}], "meta": {"total_pages": 2}},
            {"data": [{"id": "2"}], "meta": {"total_pages": 2}},
        ]
        result = _get_all_pages("invoices")
        assert len(result) == 2
        assert mock_get.call_count == 2

    @patch("services.productive_api._get")
    def test_respects_max_pages(self, mock_get):
        mock_get.return_value = {"data": [{"id": "1"}], "meta": {"total_pages": 100}}
        result = _get_all_pages("invoices", max_pages=3)
        assert mock_get.call_count == 3

    @patch("services.productive_api._get")
    def test_empty_response(self, mock_get):
        mock_get.return_value = {"data": [], "meta": {"total_pages": 1}}
        assert _get_all_pages("invoices") == []


# ── Error handling ──

class TestSafeFetch:
    def test_success(self):
        result = _safe_fetch(lambda: [1, 2, 3])
        assert result == [1, 2, 3]

    def test_http_error_raises_api_error(self):
        import requests

        def failing():
            resp = MagicMock()
            resp.status_code = 500
            raise requests.exceptions.HTTPError(response=resp)

        with pytest.raises(_ApiError, match="HTTP 500"):
            _safe_fetch(failing, label="test")

    def test_connection_error_raises_api_error(self):
        import requests

        def failing():
            raise requests.exceptions.ConnectionError("timeout")

        with pytest.raises(_ApiError, match="Verbindingsfout"):
            _safe_fetch(failing, label="test")


class TestSafeLoad:
    def test_returns_data_on_success(self):
        result = safe_load(lambda: [{"id": "1"}])
        assert result == [{"id": "1"}]

    def test_returns_empty_on_api_error(self):
        def failing():
            raise _ApiError("test error")

        result = safe_load(failing)
        assert result == []
