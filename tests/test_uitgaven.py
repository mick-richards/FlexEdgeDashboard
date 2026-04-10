"""Tests for pages/2_Uitgaven.py — auto-categorization and tx key generation.

We import the functions and constants directly to avoid triggering Streamlit UI code.
"""
from __future__ import annotations

import importlib
import sys
import types

import pytest


# ── Helpers: import _categorize / _make_tx_key without running Streamlit page code ──

def _load_uitgaven_functions():
    """Extract _categorize, _make_tx_key, and CATEGORY_RULES from the page module source
    without executing Streamlit page-level code."""
    from pathlib import Path
    source = (Path(__file__).parent.parent / "pages" / "2_Uitgaven.py").read_text(encoding="utf-8")

    # Only execute the safe parts: imports, constants, and function defs.
    # Cut off at the first bare `if not bank_configured()` which starts page execution.
    safe_source = source.split("\nif not bank_configured():")[0]

    # Provide lightweight stubs for imports that need Streamlit / bank_api
    fake_st = types.ModuleType("streamlit")
    fake_st.markdown = lambda *a, **k: None
    fake_st.caption = lambda *a, **k: None
    fake_bank = types.ModuleType("services.bank_api")
    fake_bank.is_configured = lambda: False
    fake_bank.get_transactions = lambda *a, **k: []

    saved = {}
    for mod_name, fake in [("streamlit", fake_st), ("services.bank_api", fake_bank)]:
        saved[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = fake

    try:
        module = types.ModuleType("_uitgaven_safe")
        module.__file__ = str(Path(__file__).parent.parent / "pages" / "2_Uitgaven.py")
        exec(compile(safe_source, "pages/2_Uitgaven.py", "exec"), module.__dict__)
        return module
    finally:
        for mod_name, original in saved.items():
            if original is None:
                sys.modules.pop(mod_name, None)
            else:
                sys.modules[mod_name] = original


_mod = _load_uitgaven_functions()
_categorize = _mod._categorize
_make_tx_key = _mod._make_tx_key
CATEGORY_RULES = _mod.CATEGORY_RULES


# ── _categorize ──

class TestCategorize:
    def test_salary_keyword(self):
        assert _categorize("Netto loon april 2026") == "Salarissen"

    def test_software_anthropic(self):
        assert _categorize("ANTHROPIC PBC - invoice") == "Software & tools"

    def test_software_github(self):
        assert _categorize("GitHub Inc subscription") == "Software & tools"

    def test_kantoor(self):
        assert _categorize("SPACES huur april") == "Kantoor"

    def test_reiskosten_ns(self):
        assert _categorize("ns.nl reisproduct") == "Reiskosten"

    def test_telecom(self):
        assert _categorize("Odido maandnota") == "Telecom"

    def test_belasting(self):
        assert _categorize("Belastingdienst btw aanslag") == "Belasting"

    def test_bank(self):
        assert _categorize("Transactiekosten Q1") == "Bank"

    def test_inhuur(self):
        assert _categorize("Factuur Gerben consultancy") == "Inhuur"

    def test_marketing(self):
        assert _categorize("Lunch klant Amsterdam") == "Marketing & acquisitie"

    def test_opleiding(self):
        assert _categorize("Cursus projectmanagement") == "Opleiding"

    def test_boekhouder(self):
        assert _categorize("Slingerland administratie") == "Boekhouder"

    def test_verzekering(self):
        assert _categorize("Anker verzekeringen premie") == "Verzekeringen"

    def test_capital_goods(self):
        assert _categorize("Coolblue MacBook Pro") == "Capital Goods"

    def test_kantoorartikelen(self):
        assert _categorize("Bruna papier en inkt") == "Kantoorartikelen"

    def test_overig_fallback(self):
        assert _categorize("Random payment xyz") == "Overig"

    def test_case_insensitive(self):
        assert _categorize("ANTHROPIC payment") == "Software & tools"

    def test_empty_description(self):
        assert _categorize("") == "Overig"

    def test_every_category_has_at_least_one_match(self):
        """Ensure every category in CATEGORY_RULES can be triggered."""
        matched = set()
        for category, keywords in CATEGORY_RULES.items():
            result = _categorize(keywords[0])
            matched.add(result)
        assert matched == set(CATEGORY_RULES.keys())


# ── _make_tx_key ──

class TestMakeTxKey:
    def test_basic(self):
        row = {"date": "2026-01-15", "amount": -50.0, "description": "test"}
        assert _make_tx_key(row) == "2026-01-15|-50.0|test"

    def test_truncates_description(self):
        row = {"date": "2026-01-15", "amount": 10, "description": "A" * 100}
        key = _make_tx_key(row)
        assert key == f"2026-01-15|10|{'A' * 50}"

    def test_missing_fields(self):
        row = {}
        assert _make_tx_key(row) == "||"
