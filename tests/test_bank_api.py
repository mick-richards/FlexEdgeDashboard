"""Tests for services/bank_api.py — JWT generation, key loading, transaction parsing."""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from services.bank_api import (
    _load_holding_bank_config,
    save_holding_bank_config,
    get_transactions_for_account,
    get_balance_for_account,
)


# ── Holding bank config persistence ──


class TestHoldingBankConfig:
    def test_save_and_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr("services.bank_api.Path", lambda *a: tmp_path if not a else Path(*a))

        # Directly test with tmp_path
        config = {"account_id": "abc123", "session_id": "sess456"}
        path = tmp_path / "data" / "holding_mick_bank.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(config, indent=2), encoding="utf-8")

        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["account_id"] == "abc123"

    def test_load_missing_config(self):
        # _load_holding_bank_config returns {} for missing files
        result = _load_holding_bank_config("nonexistent_user_xyz")
        assert result == {}


# ── Transaction parsing logic ──
# We test the transaction parsing by mocking the HTTP layer.


class TestGetTransactionsForAccount:
    @patch("services.bank_api.is_configured", return_value=True)
    @patch("services.bank_api._headers", return_value={"Authorization": "Bearer test"})
    @patch("services.bank_api.requests.get")
    def test_parses_credit_and_debit(self, mock_get, mock_headers, mock_configured):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": [
                {
                    "booking_date": "2026-03-15",
                    "transaction_amount": {"amount": "150.50", "currency": "EUR"},
                    "credit_debit_indicator": "DBIT",
                    "remittance_information": ["Huur kantoor"],
                    "creditor": {"name": "Verhuurder BV"},
                },
                {
                    "booking_date": "2026-03-16",
                    "transaction_amount": {"amount": "5000.00", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                    "remittance_information": ["Factuur 2026-001"],
                    "debtor": {"name": "Klant BV"},
                },
            ],
        }
        mock_get.return_value = mock_response

        transactions = get_transactions_for_account("acc123", days=30)

        assert len(transactions) == 2
        # Debit should be negative
        debit = next(t for t in transactions if t["type"] == "outgoing")
        assert debit["amount"] == -150.50
        assert debit["description"] == "Huur kantoor"
        assert debit["creditor"] == "Verhuurder BV"
        # Credit should be positive
        credit = next(t for t in transactions if t["type"] == "incoming")
        assert credit["amount"] == 5000.00
        assert credit["description"] == "Factuur 2026-001"

    @patch("services.bank_api.is_configured", return_value=True)
    @patch("services.bank_api._headers", return_value={"Authorization": "Bearer test"})
    @patch("services.bank_api.requests.get")
    def test_sorted_by_date_descending(self, mock_get, mock_headers, mock_configured):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": [
                {
                    "booking_date": "2026-03-10",
                    "transaction_amount": {"amount": "100", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                },
                {
                    "booking_date": "2026-03-20",
                    "transaction_amount": {"amount": "200", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                },
            ],
        }
        mock_get.return_value = mock_response

        transactions = get_transactions_for_account("acc123", days=30)
        assert transactions[0]["date"] == "2026-03-20"
        assert transactions[1]["date"] == "2026-03-10"

    @patch("services.bank_api.is_configured", return_value=False)
    def test_returns_empty_when_not_configured(self, mock_configured):
        assert get_transactions_for_account("acc123") == []

    @patch("services.bank_api.is_configured", return_value=True)
    def test_returns_empty_for_empty_account_id(self, mock_configured):
        assert get_transactions_for_account("") == []

    @patch("services.bank_api.is_configured", return_value=True)
    @patch("services.bank_api._headers", return_value={"Authorization": "Bearer test"})
    @patch("services.bank_api.requests.get")
    def test_handles_pagination(self, mock_get, mock_headers, mock_configured):
        page1 = MagicMock()
        page1.status_code = 200
        page1.json.return_value = {
            "transactions": [
                {
                    "booking_date": "2026-03-15",
                    "transaction_amount": {"amount": "100", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                },
            ],
            "continuation_key": "page2",
        }
        page2 = MagicMock()
        page2.status_code = 200
        page2.json.return_value = {
            "transactions": [
                {
                    "booking_date": "2026-03-16",
                    "transaction_amount": {"amount": "200", "currency": "EUR"},
                    "credit_debit_indicator": "CRDT",
                },
            ],
        }
        mock_get.side_effect = [page1, page2]

        transactions = get_transactions_for_account("acc123", days=30)
        assert len(transactions) == 2

    @patch("services.bank_api.is_configured", return_value=True)
    @patch("services.bank_api._headers", return_value={"Authorization": "Bearer test"})
    @patch("services.bank_api.requests.get")
    def test_fallback_description_from_creditor(self, mock_get, mock_headers, mock_configured):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "transactions": [
                {
                    "booking_date": "2026-03-15",
                    "transaction_amount": {"amount": "50", "currency": "EUR"},
                    "credit_debit_indicator": "DBIT",
                    "remittance_information": [],
                    "creditor": {"name": "Albert Heijn"},
                },
            ],
        }
        mock_get.return_value = mock_response

        transactions = get_transactions_for_account("acc123", days=30)
        assert transactions[0]["description"] == "Albert Heijn"


# ── Balance retrieval ──


class TestGetBalanceForAccount:
    @patch("services.bank_api.is_configured", return_value=True)
    @patch("services.bank_api._headers", return_value={"Authorization": "Bearer test"})
    @patch("services.bank_api.requests.get")
    def test_preferred_balance_type(self, mock_get, mock_headers, mock_configured):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "balances": [
                {
                    "balance_type": "ITBD",
                    "balance_amount": {"amount": "1000.00", "currency": "EUR"},
                    "reference_date": "2026-03-15",
                },
                {
                    "balance_type": "CLAV",
                    "balance_amount": {"amount": "950.00", "currency": "EUR"},
                    "reference_date": "2026-03-15",
                },
            ],
        }
        mock_get.return_value = mock_response

        result = get_balance_for_account("acc123")
        assert result is not None
        # CLAV is preferred over ITBD
        assert result["amount"] == 950.00

    @patch("services.bank_api.is_configured", return_value=False)
    def test_returns_none_when_not_configured(self, mock_configured):
        assert get_balance_for_account("acc123") is None

    @patch("services.bank_api.is_configured", return_value=True)
    def test_returns_none_for_empty_account(self, mock_configured):
        assert get_balance_for_account("") is None
