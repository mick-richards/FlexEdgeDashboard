"""Tests for services/emissions.py — GHG Protocol calculations."""
from __future__ import annotations

import json

import pytest

from services.emissions import (
    FACTORS,
    calc_scope1,
    calc_scope2,
    calc_scope3_cat3,
    calc_scope3_cat5,
    calc_scope3_cat7,
    calc_travel_emissions,
    build_summary,
    load_scope1,
    save_scope1,
    load_scope2,
    save_scope2,
    load_commute,
    save_commute,
    load_travel_log,
    save_travel_log,
)


# ── Scope 1: Natural gas ──


class TestCalcScope1:
    def test_single_month(self):
        data = {"2026-01": {"gas_m3": 100}}
        result = calc_scope1(data)
        assert result["2026-01"] == pytest.approx(100 * 1.785)

    def test_multiple_months(self):
        data = {
            "2026-01": {"gas_m3": 100},
            "2026-02": {"gas_m3": 80},
            "2026-03": {"gas_m3": 0},
        }
        result = calc_scope1(data)
        assert len(result) == 3
        assert result["2026-03"] == 0.0

    def test_empty_data(self):
        assert calc_scope1({}) == {}

    def test_missing_gas_m3_defaults_to_zero(self):
        data = {"2026-01": {"other_field": 42}}
        result = calc_scope1(data)
        assert result["2026-01"] == 0.0


# ── Scope 2: Electricity ──


class TestCalcScope2:
    def test_non_green_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": False}}
        result = calc_scope2(data)
        expected_location = 1000 * FACTORS["electricity_kwh_location"]
        assert result["2026-01"]["location_based"] == pytest.approx(expected_location)
        assert result["2026-01"]["market_based"] == pytest.approx(expected_location)

    def test_green_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": True}}
        result = calc_scope2(data)
        assert result["2026-01"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["2026-01"]["market_based"] == 0.0

    def test_zero_kwh(self):
        data = {"2026-01": {"kwh": 0}}
        result = calc_scope2(data)
        assert result["2026-01"]["location_based"] == 0.0
        assert result["2026-01"]["market_based"] == 0.0

    def test_missing_green_defaults_to_non_green(self):
        data = {"2026-01": {"kwh": 500}}
        result = calc_scope2(data)
        # green defaults to False → market_based == location_based
        assert result["2026-01"]["market_based"] == result["2026-01"]["location_based"]


# ── Scope 3 Cat 3: WTT uplift ──


class TestCalcScope3Cat3:
    def test_wtt_uplift(self):
        result = calc_scope3_cat3(1000, 500)
        expected = 1000 * 0.15 + 500 * 0.10
        assert result == pytest.approx(expected)

    def test_zero_inputs(self):
        assert calc_scope3_cat3(0, 0) == 0.0


# ── Scope 3 Cat 5: Waste ──


class TestCalcScope3Cat5:
    def test_single_fte(self):
        result = calc_scope3_cat5(1.0)
        expected = 1.0 * 15.0 * 0.5 * 12
        assert result == pytest.approx(expected)

    def test_fractional_fte(self):
        result = calc_scope3_cat5(3.5)
        expected = 3.5 * 15.0 * 0.5 * 12
        assert result == pytest.approx(expected)

    def test_zero_fte(self):
        assert calc_scope3_cat5(0) == 0.0


# ── Scope 3 Cat 7: Commuting ──


class TestCalcScope3Cat7:
    def test_single_employee_train(self):
        employees = [{
            "name": "Alice",
            "distance_km": 30,
            "days_per_week": 4,
            "mode": "Trein (NS)",
            "weeks_per_year": 46,
        }]
        result = calc_scope3_cat7(employees)
        # 30km * 2 (round trip) * 4 days * 46 weeks * 0.008
        expected = 30 * 2 * 4 * 46 * 0.008
        assert result == pytest.approx(expected)

    def test_default_weeks_per_year(self):
        employees = [{"distance_km": 10, "days_per_week": 5, "mode": "Fiets"}]
        result = calc_scope3_cat7(employees)
        # Fiets factor = 0.0, so total should be 0
        assert result == 0.0

    def test_car_commute(self):
        employees = [{
            "distance_km": 25,
            "days_per_week": 5,
            "mode": "Auto (benzine)",
            "weeks_per_year": 46,
        }]
        result = calc_scope3_cat7(employees)
        expected = 25 * 2 * 5 * 46 * 0.19
        assert result == pytest.approx(expected)

    def test_multiple_employees(self):
        employees = [
            {"distance_km": 10, "days_per_week": 5, "mode": "Trein (NS)", "weeks_per_year": 46},
            {"distance_km": 20, "days_per_week": 3, "mode": "Auto (elektrisch)", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        e1 = 10 * 2 * 5 * 46 * 0.008
        e2 = 20 * 2 * 3 * 46 * 0.05
        assert result == pytest.approx(e1 + e2)

    def test_empty_employees(self):
        assert calc_scope3_cat7([]) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        employees = [{"distance_km": 10, "days_per_week": 5, "mode": "Onbekend"}]
        result = calc_scope3_cat7(employees)
        expected = 10 * 2 * 5 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)


# ── Scope 3 Cat 6: Business travel ──


class TestCalcTravelEmissions:
    def test_train_trip(self):
        trips = [{"distance_km": 120, "mode": "Trein"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(120 * 0.008)

    def test_short_flight(self):
        trips = [{"distance_km": 500, "mode": "Vlucht (<800 km)"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(500 * 0.18)

    def test_long_flight(self):
        trips = [{"distance_km": 5000, "mode": "Vlucht (>800 km)"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(5000 * 0.11)

    def test_multiple_trips(self):
        trips = [
            {"distance_km": 60, "mode": "Trein"},
            {"distance_km": 200, "mode": "Auto (benzine)"},
        ]
        result = calc_travel_emissions(trips)
        expected = 60 * 0.008 + 200 * 0.19
        assert result == pytest.approx(expected)

    def test_empty_trips(self):
        assert calc_travel_emissions([]) == 0.0

    def test_missing_distance_defaults_to_zero(self):
        trips = [{"mode": "Trein"}]
        assert calc_travel_emissions(trips) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        trips = [{"distance_km": 100, "mode": "Onbekend"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(100 * FACTORS["travel_train"])


# ── Build summary (integration) ──


class TestBuildSummary:
    def test_complete_summary(self):
        scope1_data = {"2026-01": {"gas_m3": 100}}
        scope2_data = {"2026-01": {"kwh": 1000, "green": False}}
        commute = [{"distance_km": 20, "days_per_week": 5, "mode": "Trein (NS)", "weeks_per_year": 46}]
        travel = [{"distance_km": 120, "mode": "Trein"}]

        result = build_summary(
            scope1_data=scope1_data,
            scope2_data=scope2_data,
            commute_employees=commute,
            travel_trips=travel,
            fte_count=3.0,
        )

        assert result["scope1"]["total"] == pytest.approx(100 * 1.785)
        assert result["scope2"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["scope2"]["market_based"] == pytest.approx(1000 * 0.328)
        assert result["scope3"]["cat6_business_travel"] == pytest.approx(120 * 0.008)
        assert result["scope3"]["cat5_waste"] == pytest.approx(3.0 * 15 * 0.5 * 12)
        assert "total_location" in result
        assert "total_market" in result

    def test_empty_summary(self):
        result = build_summary({}, {}, [], [], 0)
        assert result["scope1"]["total"] == 0.0
        assert result["scope2"]["location_based"] == 0.0
        assert result["scope3"]["total"] == 0.0
        assert result["total_location"] == 0.0

    def test_summary_with_expense_scope3(self):
        result = build_summary(
            scope1_data={},
            scope2_data={},
            commute_employees=[],
            travel_trips=[],
            fte_count=0,
            expense_scope3={"Cat 1 - Purchased Goods": 50.0, "Cat 2 - Capital": 30.0},
        )
        assert result["scope3"]["cat1_purchased_goods_services"] == pytest.approx(50.0)
        assert result["scope3"]["cat2_capital_goods"] == pytest.approx(30.0)

    def test_total_location_vs_market(self):
        result = build_summary(
            scope1_data={"2026-01": {"gas_m3": 50}},
            scope2_data={"2026-01": {"kwh": 500, "green": True}},
            commute_employees=[],
            travel_trips=[],
            fte_count=1,
        )
        # With green electricity, market_based = 0, so total_market < total_location
        assert result["total_market"] < result["total_location"]


# ── Data persistence ──


class TestDataPersistence:
    def test_save_and_load_scope1(self, tmp_data_dir):
        data = {"2026-01": {"gas_m3": 100}}
        save_scope1(data)
        loaded = load_scope1()
        assert loaded == data

    def test_load_scope1_missing_file(self, tmp_data_dir):
        assert load_scope1() == {}

    def test_save_and_load_scope2(self, tmp_data_dir):
        data = {"2026-01": {"kwh": 500, "green": True}}
        save_scope2(data)
        loaded = load_scope2()
        assert loaded == data

    def test_save_and_load_commute(self, tmp_data_dir):
        employees = [{"name": "Alice", "distance_km": 20}]
        save_commute(employees)
        loaded = load_commute()
        assert loaded == employees

    def test_load_commute_missing_file(self, tmp_data_dir):
        assert load_commute() == []

    def test_save_and_load_travel_log(self, tmp_data_dir):
        trips = [{"distance_km": 120, "mode": "Trein", "date": "2026-01-15"}]
        save_travel_log(trips)
        loaded = load_travel_log()
        assert loaded == trips

    def test_load_travel_log_missing_file(self, tmp_data_dir):
        assert load_travel_log() == []
