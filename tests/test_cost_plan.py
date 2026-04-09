"""Tests for services.cost_plan — month-keyed plan storage, rolling windows, and legacy compat."""
from __future__ import annotations

import json
from datetime import date

from services.cost_plan import (
    _DEFAULT_RECURRING,
    add_one_off,
    all_used_leaves,
    auto_close_past_months,
    current_ym,
    drop_category_everywhere,
    ensure_month,
    get_actuals,
    get_one_offs,
    get_recurring,
    history_months,
    is_closed,
    legacy_year_view,
    load_plan,
    mark_closed,
    month_total,
    month_total_actual,
    month_total_oneoff,
    month_total_recurring,
    remove_one_off,
    rename_category_everywhere,
    rolling_months,
    save_plan,
    set_actuals,
    set_recurring_cell,
    ym_add,
    ym_to_label,
)


# ── I/O ─────────────────────────────────────────────────────────────────────

class TestLoadSave:
    def test_load_empty_when_no_file(self, cost_plan_file):
        plan = load_plan()
        assert plan["schema_version"] == 2
        assert plan["months"] == {}

    def test_roundtrip(self, cost_plan_file):
        plan = {"schema_version": 2, "months": {"2026-01": {"recurring": {"X": 100}, "actuals": {}, "one_offs": [], "closed": False}}}
        save_plan(plan)
        loaded = load_plan()
        assert loaded["months"]["2026-01"]["recurring"]["X"] == 100

    def test_legacy_migration(self, cost_plan_file):
        legacy = {
            "categories": {"Kantoor": [100] * 12},
            "one_offs": [{"month": 0, "description": "Laptop", "amount": 1500}],
        }
        cost_plan_file.write_text(json.dumps(legacy), encoding="utf-8")
        plan = load_plan()
        assert "months" in plan
        assert plan["months"]["2026-01"]["recurring"]["Kantoor"] == 100.0
        assert len(plan["months"]["2026-01"]["one_offs"]) == 1


# ── Month key helpers ───────────────────────────────────────────────────────

class TestYmHelpers:
    def test_current_ym(self):
        assert current_ym(date(2026, 4, 9)) == "2026-04"

    def test_ym_add_forward(self):
        assert ym_add("2026-01", 3) == "2026-04"

    def test_ym_add_cross_year(self):
        assert ym_add("2026-11", 3) == "2027-02"

    def test_ym_add_backward(self):
        assert ym_add("2026-03", -3) == "2025-12"

    def test_ym_to_label(self):
        assert ym_to_label("2026-01") == "Jan 2026"
        assert ym_to_label("2026-12") == "Dec 2026"

    def test_rolling_months(self):
        months = rolling_months(n=3, today=date(2026, 11, 1))
        assert months == ["2026-11", "2026-12", "2027-01"]

    def test_history_months(self):
        hist = history_months(today=date(2026, 4, 1), start="2026-01")
        assert hist == ["2026-01", "2026-02", "2026-03"]

    def test_history_months_empty_if_at_start(self):
        assert history_months(today=date(2026, 1, 1), start="2026-01") == []


# ── ensure_month() ──────────────────────────────────────────────────────────

class TestEnsureMonth:
    def test_creates_with_defaults_when_no_prev(self, cost_plan_file):
        plan = load_plan()
        month = ensure_month(plan, "2026-01")
        assert month["recurring"] == _DEFAULT_RECURRING
        assert month["actuals"] == {}
        assert month["one_offs"] == []
        assert month["closed"] is False

    def test_seeds_from_previous_month(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        plan["months"]["2026-01"]["recurring"]["Kantoor"] = 999.0
        month = ensure_month(plan, "2026-02")
        assert month["recurring"]["Kantoor"] == 999.0

    def test_existing_month_untouched(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        plan["months"]["2026-01"]["recurring"]["Kantoor"] = 42.0
        # Call again — should NOT overwrite
        month = ensure_month(plan, "2026-01")
        assert month["recurring"]["Kantoor"] == 42.0


# ── Recurring / actuals / one-offs ──────────────────────────────────────────

class TestRecurring:
    def test_get_set_recurring(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-03")
        set_recurring_cell(plan, "2026-03", "Kantoor", 750.0)
        assert get_recurring(plan, "2026-03")["Kantoor"] == 750.0

    def test_get_recurring_missing_month(self, cost_plan_file):
        plan = load_plan()
        assert get_recurring(plan, "2099-01") == {}


class TestActuals:
    def test_set_and_get(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-03")
        set_actuals(plan, "2026-03", {"Kantoor": 487.30, "Software & tools": 120.0})
        act = get_actuals(plan, "2026-03")
        assert act["Kantoor"] == 487.30


class TestOneOffs:
    def test_add_and_get(self, cost_plan_file):
        plan = load_plan()
        add_one_off(plan, "2026-01", "Laptop", 1500.0)
        oos = get_one_offs(plan, "2026-01")
        assert len(oos) == 1
        assert oos[0]["description"] == "Laptop"
        assert oos[0]["amount"] == 1500.0

    def test_remove_by_index(self, cost_plan_file):
        plan = load_plan()
        add_one_off(plan, "2026-01", "A", 100)
        add_one_off(plan, "2026-01", "B", 200)
        remove_one_off(plan, "2026-01", 0)
        assert len(get_one_offs(plan, "2026-01")) == 1
        assert get_one_offs(plan, "2026-01")[0]["description"] == "B"

    def test_remove_invalid_index_noop(self, cost_plan_file):
        plan = load_plan()
        add_one_off(plan, "2026-01", "A", 100)
        remove_one_off(plan, "2026-01", 5)  # out of range
        assert len(get_one_offs(plan, "2026-01")) == 1


# ── Close / variance ───────────────────────────────────────────────────────

class TestCloseAndTotals:
    def test_close_and_check(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        assert not is_closed(plan, "2026-01")
        mark_closed(plan, "2026-01")
        assert is_closed(plan, "2026-01")

    def test_totals(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        # Clear seeded defaults so we control the exact values
        plan["months"]["2026-01"]["recurring"] = {}
        set_recurring_cell(plan, "2026-01", "A", 100)
        set_recurring_cell(plan, "2026-01", "B", 200)
        add_one_off(plan, "2026-01", "C", 50)
        set_actuals(plan, "2026-01", {"A": 90, "B": 210})

        assert month_total_recurring(plan, "2026-01") == 300.0
        assert month_total_oneoff(plan, "2026-01") == 50.0
        assert month_total(plan, "2026-01") == 350.0
        assert month_total_actual(plan, "2026-01") == 300.0


# ── Category management ────────────────────────────────────────────────────

class TestCategoryManagement:
    def test_all_used_leaves(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        set_recurring_cell(plan, "2026-01", "Kantoor", 100)
        set_actuals(plan, "2026-01", {"Software & tools": 50})
        used = all_used_leaves(plan)
        assert "Kantoor" in used
        assert "Software & tools" in used

    def test_drop_category(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        set_recurring_cell(plan, "2026-01", "Kantoor", 100)
        set_actuals(plan, "2026-01", {"Kantoor": 90})
        drop_category_everywhere(plan, "Kantoor")
        assert "Kantoor" not in get_recurring(plan, "2026-01")
        assert "Kantoor" not in get_actuals(plan, "2026-01")

    def test_rename_category(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        set_recurring_cell(plan, "2026-01", "Old", 100)
        set_actuals(plan, "2026-01", {"Old": 90})
        rename_category_everywhere(plan, "Old", "New")
        assert "New" in get_recurring(plan, "2026-01")
        assert "New" in get_actuals(plan, "2026-01")
        assert "Old" not in get_recurring(plan, "2026-01")


# ── Legacy compat ───────────────────────────────────────────────────────────

class TestLegacyYearView:
    def test_produces_12_values_per_leaf(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        set_recurring_cell(plan, "2026-01", "Kantoor", 800)
        save_plan(plan)

        view = legacy_year_view(2026, plan)
        assert "Kantoor" in view["categories"]
        vals = view["categories"]["Kantoor"]
        assert len(vals) == 12
        assert vals[0] == 800.0  # jan

    def test_closed_month_uses_actuals(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        set_recurring_cell(plan, "2026-01", "Kantoor", 800)
        set_actuals(plan, "2026-01", {"Kantoor": 750})
        mark_closed(plan, "2026-01")

        view = legacy_year_view(2026, plan)
        assert view["categories"]["Kantoor"][0] == 750.0

    def test_one_offs_mapped(self, cost_plan_file):
        plan = load_plan()
        add_one_off(plan, "2026-03", "Laptop", 1500)
        save_plan(plan)

        view = legacy_year_view(2026, plan)
        assert any(oo["month"] == 2 and oo["description"] == "Laptop" for oo in view["one_offs"])


# ── Auto-close ──────────────────────────────────────────────────────────────

class TestAutoClose:
    def test_closes_past_months(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        ensure_month(plan, "2026-02")
        ensure_month(plan, "2026-04")
        newly = auto_close_past_months(plan, today=date(2026, 4, 1))
        assert "2026-01" in newly
        assert "2026-02" in newly
        assert "2026-04" not in newly  # current month

    def test_already_closed_not_re_reported(self, cost_plan_file):
        plan = load_plan()
        ensure_month(plan, "2026-01")
        mark_closed(plan, "2026-01")
        newly = auto_close_past_months(plan, today=date(2026, 4, 1))
        assert "2026-01" not in newly
