"""Tests for services/productive_api.py — API helpers and data parsing."""
from __future__ import annotations

from unittest.mock import patch, MagicMock
from datetime import date

import pytest
import requests

from services.productive_api import (
    _invoice_status,
    _get_all_pages,
    _safe_fetch,
    _ApiError,
    safe_load,
    build_lookup,
)


# ── Invoice status logic ──


class TestInvoiceStatus:
    def test_paid(self):
        assert _invoice_status({"paid_date": "2026-01-15"}) == "paid"

    def test_overdue(self):
        # Use a date in the past
        assert _invoice_status({"due_date": "2020-01-01"}) == "overdue"

    def test_sent(self):
        # Due date in the future, has a date, not paid
        assert _invoice_status({"date": "2026-04-01", "due_date": "2099-12-31"}) == "sent"

    def test_draft(self):
        assert _invoice_status({}) == "draft"

    def test_paid_takes_precedence_over_overdue(self):
        attrs = {"paid_date": "2026-03-01", "due_date": "2020-01-01"}
        assert _invoice_status(attrs) == "paid"


# ── build_lookup ──


class TestBuildLookup:
    def test_basic_lookup(self):
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


# ── _get_all_pages (with mocked _get) ──


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


# ── _safe_fetch error handling ──


class TestSafeFetch:
    def test_successful_fetch(self):
        result = _safe_fetch(lambda: [1, 2, 3], label="test")
        assert result == [1, 2, 3]

    def test_http_error_raises_api_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        def bad_fetch():
            raise requests.exceptions.HTTPError(response=mock_response)

        with pytest.raises(_ApiError, match="Kon test niet laden"):
            _safe_fetch(bad_fetch, label="test")

    def test_connection_error_raises_api_error(self):
        def bad_fetch():
            raise requests.exceptions.ConnectionError("timeout")

        with pytest.raises(_ApiError, match="Verbindingsfout"):
            _safe_fetch(bad_fetch, label="test")


# ── safe_load wrapper ──


class TestSafeLoad:
    @patch("services.productive_api.st")
    def test_catches_api_error_returns_empty(self, mock_st):
        def bad_fetch():
            raise _ApiError("Fout!")

        result = safe_load(bad_fetch)
        assert result == []
        mock_st.warning.assert_called_once_with("Fout!")

    def test_passes_through_successful_result(self):
        result = safe_load(lambda: [{"id": "1"}])
        assert result == [{"id": "1"}]
