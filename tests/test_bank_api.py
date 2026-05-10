"""Tests for services/bank_api.py — Enable Banking client."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from services.bank_api import (
    get_balance_for_account,
    get_transactions_for_account,
    save_holding_bank_config,
    _load_holding_bank_config,
)

# All tests that call the API need _headers mocked to avoid JWT signing with a fake key.
MOCK_HEADERS = {"Authorization": "Bearer fake", "Content-Type": "application/json"}


def _api_patches():
    """Stack patches for is_configured + _headers so API calls don't need real credentials."""
    return [
        patch("services.bank_api.is_configured", return_value=True),
        patch("services.bank_api._headers", return_value=MOCK_HEADERS),
    ]


# ── Balance type priority ──

class TestGetBalanceForAccount:
    @patch("services.bank_api.requests.get")
    def test_prefers_clav_over_others(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"balances": [
                    {"balance_type": "ITBD", "balance_amount": {"amount": "100", "currency": "EUR"}, "reference_date": "2026-01-01"},
                    {"balance_type": "CLAV", "balance_amount": {"amount": "200", "currency": "EUR"}, "reference_date": "2026-01-01"},
                ]},
            )
            result = get_balance_for_account("acc123")
            assert result["amount"] == 200.0

    @patch("services.bank_api.requests.get")
    def test_fallback_to_first_balance(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"balances": [
                    {"balance_type": "UNKNOWN", "balance_amount": {"amount": "50", "currency": "EUR"}, "reference_date": "2026-01-01"},
                ]},
            )
            result = get_balance_for_account("acc123")
            assert result["amount"] == 50.0

    @patch("services.bank_api.requests.get")
    def test_empty_balances(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"balances": []},
            )
            assert get_balance_for_account("acc123") is None

    @patch("services.bank_api.requests.get")
    def test_non_200_returns_none(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(status_code=401)
            assert get_balance_for_account("acc123") is None

    def test_empty_account_id(self):
        assert get_balance_for_account("") is None

    @patch("services.bank_api.is_configured", return_value=False)
    def test_not_configured(self, _):
        assert get_balance_for_account("acc123") is None


# ── Transaction normalization ──

class TestGetTransactionsForAccount:
    @patch("services.bank_api.requests.get")
    def test_debit_is_negative(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "transactions": [{
                        "booking_date": "2026-01-15",
                        "transaction_amount": {"amount": "100.50", "currency": "EUR"},
                        "credit_debit_indicator": "DBIT",
                        "remittance_information": ["Payment to vendor"],
                        "creditor": {"name": "Vendor Inc"},
                    }],
                    "continuation_key": None,
                },
            )
            result = get_transactions_for_account("acc123", days=30)
            assert len(result) == 1
            assert result[0]["amount"] == -100.50
            assert result[0]["type"] == "outgoing"
            assert result[0]["description"] == "Payment to vendor"

    @patch("services.bank_api.requests.get")
    def test_credit_is_positive(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "transactions": [{
                        "booking_date": "2026-01-15",
                        "transaction_amount": {"amount": "500", "currency": "EUR"},
                        "credit_debit_indicator": "CRDT",
                        "remittance_information": [],
                        "debtor": {"name": "Client BV"},
                    }],
                    "continuation_key": None,
                },
            )
            result = get_transactions_for_account("acc123", days=30)
            assert result[0]["amount"] == 500.0
            assert result[0]["type"] == "incoming"
            assert result[0]["description"] == "Client BV"

    @patch("services.bank_api.requests.get")
    def test_pagination(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.side_effect = [
                MagicMock(status_code=200, json=lambda: {
                    "transactions": [{"booking_date": "2026-01-15", "transaction_amount": {"amount": "10", "currency": "EUR"},
                                      "credit_debit_indicator": "CRDT", "remittance_information": ["A"]}],
                    "continuation_key": "page2",
                }),
                MagicMock(status_code=200, json=lambda: {
                    "transactions": [{"booking_date": "2026-01-14", "transaction_amount": {"amount": "20", "currency": "EUR"},
                                      "credit_debit_indicator": "CRDT", "remittance_information": ["B"]}],
                    "continuation_key": None,
                }),
            ]
            result = get_transactions_for_account("acc123", days=30)
            assert len(result) == 2
            assert result[0]["date"] == "2026-01-15"
            assert result[1]["date"] == "2026-01-14"

    @patch("services.bank_api.requests.get")
    def test_sorted_by_date_descending(self, mock_get):
        with patch("services.bank_api.is_configured", return_value=True), \
             patch("services.bank_api._headers", return_value=MOCK_HEADERS):
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "transactions": [
                        {"booking_date": "2026-01-10", "transaction_amount": {"amount": "1", "currency": "EUR"},
                         "credit_debit_indicator": "CRDT", "remittance_information": ["Old"]},
                        {"booking_date": "2026-01-20", "transaction_amount": {"amount": "2", "currency": "EUR"},
                         "credit_debit_indicator": "CRDT", "remittance_information": ["New"]},
                    ],
                    "continuation_key": None,
                },
            )
            result = get_transactions_for_account("acc123")
            assert result[0]["date"] == "2026-01-20"
            assert result[1]["date"] == "2026-01-10"

    def test_empty_account_id(self):
        assert get_transactions_for_account("") == []


# ── Holding bank config persistence ──

class TestHoldingBankConfig:
    def test_load_nonexistent(self):
        result = _load_holding_bank_config("nonexistent_user_xyz_99")
        assert result == {}
