"""Tests for services.actuals — categorisation and monthly aggregation."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from services.actuals import (
    CATEGORY_RULES,
    _ym,
    actuals_for_month,
    actuals_per_month,
    categorise,
    income_per_month,
    make_tx_key,
)


# ── categorise() ────────────────────────────────────────────────────────────

class TestCategorise:
    @pytest.mark.parametrize("desc, expected", [
        ("Salaris maart 2026", "Salarissen"),
        ("LOONHEFFING Q1", "Salarissen"),
        ("Anthropic invoice #42", "Software & tools"),
        ("NS.nl reisproduct", "Reiskosten"),
        ("Spaces factuur", "Kantoor"),
        ("random gibberish", "Overig"),
        ("", "Overig"),
        (None, "Overig"),
    ])
    def test_keyword_matching(self, desc, expected):
        assert categorise(desc) == expected

    def test_case_insensitive(self):
        assert categorise("GITHUB COPILOT") == "Software & tools"

    def test_all_rules_have_at_least_one_keyword(self):
        for parent, keywords in CATEGORY_RULES.items():
            assert len(keywords) > 0, f"{parent} has no keywords"


# ── make_tx_key() ───────────────────────────────────────────────────────────

class TestMakeTxKey:
    def test_basic(self):
        row = {"date": "2026-03-01", "amount": -500.0, "description": "Test payment"}
        key = make_tx_key(row)
        assert "2026-03-01" in key
        assert "-500.0" in key
        assert "Test payment" in key

    def test_truncates_long_description(self):
        row = {"date": "2026-01-01", "amount": 0, "description": "x" * 100}
        key = make_tx_key(row)
        # Description part should be at most 50 chars
        desc_part = key.split("|")[2]
        assert len(desc_part) == 50

    def test_missing_fields(self):
        key = make_tx_key({})
        assert key == "||"


# ── _ym() ───────────────────────────────────────────────────────────────────

class TestYm:
    def test_from_string(self):
        assert _ym("2026-03-15") == "2026-03"

    def test_from_date(self):
        from datetime import date
        assert _ym(date(2026, 1, 5)) == "2026-01"

    def test_from_iso_datetime(self):
        assert _ym("2026-12-31T23:59:59") == "2026-12"


# ── actuals_per_month() ────────────────────────────────────────────────────

SAMPLE_TXS = [
    {"date": "2026-03-01", "amount": -500.0, "description": "Salaris maart"},
    {"date": "2026-03-05", "amount": -120.0, "description": "GitHub Copilot"},
    {"date": "2026-03-10", "amount": 5000.0, "description": "Klantbetaling"},
    {"date": "2026-02-15", "amount": -800.0, "description": "Spaces huur feb"},
]


class TestActualsPerMonth:
    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=SAMPLE_TXS)
    def test_groups_by_month_and_category(self, mock_txs, mock_conf, overrides_file):
        result = actuals_per_month(days=365)
        assert "2026-03" in result
        assert "2026-02" in result
        assert result["2026-03"]["Salarissen"] == 500.0
        assert result["2026-03"]["Software & tools"] == 120.0
        assert result["2026-02"]["Kantoor"] == 800.0

    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=SAMPLE_TXS)
    def test_ignores_income(self, mock_txs, mock_conf, overrides_file):
        result = actuals_per_month()
        # The 5000 income tx should not appear
        for cats in result.values():
            assert all(v > 0 for v in cats.values())

    @patch("services.actuals.bank_configured", return_value=False)
    def test_returns_empty_when_not_configured(self, mock_conf):
        assert actuals_per_month() == {}

    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=[])
    def test_returns_empty_for_no_transactions(self, mock_txs, mock_conf):
        assert actuals_per_month() == {}

    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=[
        {"date": "2026-03-01", "amount": -100.0, "description": "Overig dingetje"},
    ])
    def test_override_wins_over_keyword(self, mock_txs, mock_conf, overrides_file):
        # Write an override for this tx
        key = make_tx_key({"date": "2026-03-01", "amount": -100.0, "description": "Overig dingetje"})
        overrides_file.write_text(json.dumps({key: "Kantoor"}), encoding="utf-8")

        result = actuals_per_month()
        assert result["2026-03"]["Kantoor"] == 100.0
        assert "Overig" not in result.get("2026-03", {})


# ── actuals_for_month() ────────────────────────────────────────────────────

class TestActualsForMonth:
    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=SAMPLE_TXS)
    def test_returns_single_month(self, mock_txs, mock_conf, overrides_file):
        result = actuals_for_month("2026-03")
        assert "Salarissen" in result
        assert "Kantoor" not in result  # that was feb

    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=[])
    def test_missing_month_returns_empty(self, mock_txs, mock_conf):
        assert actuals_for_month("2099-01") == {}


# ── income_per_month() ─────────────────────────────────────────────────────

class TestIncomePerMonth:
    @patch("services.actuals.bank_configured", return_value=True)
    @patch("services.actuals.get_transactions", return_value=SAMPLE_TXS)
    def test_sums_positive_amounts(self, mock_txs, mock_conf):
        result = income_per_month()
        assert result["2026-03"] == 5000.0
        assert "2026-02" not in result  # no income that month

    @patch("services.actuals.bank_configured", return_value=False)
    def test_not_configured(self, mock_conf):
        assert income_per_month() == {}
