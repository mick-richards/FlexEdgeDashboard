"""Tests for services/emissions.py — GHG Protocol calculations."""
from __future__ import annotations

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
)


# ── Scope 1 ──

class TestCalcScope1:
    def test_single_month(self):
        data = {"2026-01": {"gas_m3": 100}}
        result = calc_scope1(data)
        assert result == {"2026-01": 100 * 1.785}

    def test_multiple_months(self):
        data = {
            "2026-01": {"gas_m3": 50},
            "2026-02": {"gas_m3": 30},
        }
        result = calc_scope1(data)
        assert result["2026-01"] == pytest.approx(50 * 1.785)
        assert result["2026-02"] == pytest.approx(30 * 1.785)

    def test_zero_gas(self):
        data = {"2026-03": {"gas_m3": 0}}
        assert calc_scope1(data) == {"2026-03": 0.0}

    def test_missing_gas_key(self):
        data = {"2026-04": {}}
        assert calc_scope1(data) == {"2026-04": 0.0}

    def test_empty_data(self):
        assert calc_scope1({}) == {}


# ── Scope 2 ──

class TestCalcScope2:
    def test_grey_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": False}}
        result = calc_scope2(data)
        expected_location = 1000 * 0.328
        assert result["2026-01"]["location_based"] == pytest.approx(expected_location)
        assert result["2026-01"]["market_based"] == pytest.approx(expected_location)

    def test_green_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": True}}
        result = calc_scope2(data)
        assert result["2026-01"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["2026-01"]["market_based"] == 0.0

    def test_zero_kwh(self):
        data = {"2026-01": {"kwh": 0, "green": False}}
        result = calc_scope2(data)
        assert result["2026-01"]["location_based"] == 0.0
        assert result["2026-01"]["market_based"] == 0.0

    def test_missing_green_defaults_false(self):
        data = {"2026-01": {"kwh": 500}}
        result = calc_scope2(data)
        expected = 500 * 0.328
        assert result["2026-01"]["location_based"] == pytest.approx(expected)
        assert result["2026-01"]["market_based"] == pytest.approx(expected)

    def test_empty_data(self):
        assert calc_scope2({}) == {}


# ── Scope 3 Cat 3: WTT uplift ──

class TestCalcScope3Cat3:
    def test_basic(self):
        result = calc_scope3_cat3(1000.0, 2000.0)
        assert result == pytest.approx(1000 * 0.15 + 2000 * 0.10)

    def test_zeros(self):
        assert calc_scope3_cat3(0, 0) == 0.0


# ── Scope 3 Cat 5: Waste ──

class TestCalcScope3Cat5:
    def test_one_fte(self):
        result = calc_scope3_cat5(1.0)
        assert result == pytest.approx(1.0 * 15.0 * 0.5 * 12)

    def test_fractional_fte(self):
        result = calc_scope3_cat5(2.5)
        assert result == pytest.approx(2.5 * 15.0 * 0.5 * 12)

    def test_zero_fte(self):
        assert calc_scope3_cat5(0) == 0.0


# ── Scope 3 Cat 7: Commuting ──

class TestCalcScope3Cat7:
    def test_single_employee_train(self):
        employees = [
            {"name": "Alice", "distance_km": 25, "days_per_week": 4,
             "mode": "Trein (NS)", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        expected = 25 * 2 * 4 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)

    def test_default_weeks(self):
        employees = [
            {"name": "Bob", "distance_km": 10, "days_per_week": 5,
             "mode": "Fiets"},
        ]
        result = calc_scope3_cat7(employees)
        assert result == 0.0  # bike = 0 factor

    def test_multiple_employees(self):
        employees = [
            {"name": "A", "distance_km": 20, "days_per_week": 3,
             "mode": "Auto (benzine)", "weeks_per_year": 46},
            {"name": "B", "distance_km": 15, "days_per_week": 5,
             "mode": "Trein (NS)", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        expected_a = 20 * 2 * 3 * 46 * FACTORS["commute_car_petrol"]
        expected_b = 15 * 2 * 5 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected_a + expected_b)

    def test_empty_list(self):
        assert calc_scope3_cat7([]) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        employees = [
            {"name": "C", "distance_km": 10, "days_per_week": 2,
             "mode": "Raket", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        expected = 10 * 2 * 2 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)


# ── Scope 3 Cat 6: Business travel ──

class TestCalcTravelEmissions:
    def test_train_trip(self):
        trips = [{"distance_km": 60, "mode": "Trein"}]
        assert calc_travel_emissions(trips) == pytest.approx(60 * 0.008)

    def test_short_flight(self):
        trips = [{"distance_km": 500, "mode": "Vlucht (<800 km)"}]
        assert calc_travel_emissions(trips) == pytest.approx(500 * 0.18)

    def test_long_flight(self):
        trips = [{"distance_km": 2000, "mode": "Vlucht (>800 km)"}]
        assert calc_travel_emissions(trips) == pytest.approx(2000 * 0.11)

    def test_multiple_trips(self):
        trips = [
            {"distance_km": 60, "mode": "Trein"},
            {"distance_km": 100, "mode": "Auto (benzine)"},
        ]
        expected = 60 * 0.008 + 100 * 0.19
        assert calc_travel_emissions(trips) == pytest.approx(expected)

    def test_empty(self):
        assert calc_travel_emissions([]) == 0.0

    def test_missing_distance(self):
        trips = [{"mode": "Trein"}]
        assert calc_travel_emissions(trips) == 0.0


# ── Build summary ──

class TestBuildSummary:
    def test_full_summary(self):
        scope1_data = {"2026-01": {"gas_m3": 100}}
        scope2_data = {"2026-01": {"kwh": 500, "green": False}}
        commute = [
            {"name": "A", "distance_km": 20, "days_per_week": 4,
             "mode": "Trein (NS)", "weeks_per_year": 46},
        ]
        travel = [{"distance_km": 60, "mode": "Trein"}]
        fte = 2.0

        result = build_summary(scope1_data, scope2_data, commute, travel, fte)

        s1 = 100 * 1.785
        s2_loc = 500 * 0.328
        s3_cat3 = s1 * 0.15 + s2_loc * 0.10
        s3_cat5 = 2.0 * 15 * 0.5 * 12
        s3_cat6 = 60 * 0.008
        s3_cat7 = 20 * 2 * 4 * 46 * 0.008

        assert result["scope1"]["total"] == pytest.approx(s1)
        assert result["scope2"]["location_based"] == pytest.approx(s2_loc)
        assert result["scope2"]["market_based"] == pytest.approx(s2_loc)  # not green
        assert result["scope3"]["cat3_fuel_energy_wtt"] == pytest.approx(s3_cat3)
        assert result["scope3"]["cat5_waste"] == pytest.approx(s3_cat5)
        assert result["scope3"]["cat6_business_travel"] == pytest.approx(s3_cat6)
        assert result["scope3"]["cat7_commuting"] == pytest.approx(s3_cat7)

    def test_with_expense_scope3(self):
        result = build_summary({}, {}, [], [], 1.0, expense_scope3={
            "Cat 1: Purchased Services": 50.0,
            "Cat 2: Capital Goods": 30.0,
            "Cat 8: Upstream Leased Assets": 20.0,
        })
        assert result["scope3"]["cat1_purchased_goods_services"] == pytest.approx(50.0)
        assert result["scope3"]["cat2_capital_goods"] == pytest.approx(30.0)
        assert result["scope3"]["cat8_leased_assets"] == pytest.approx(20.0)

    def test_empty_inputs(self):
        result = build_summary({}, {}, [], [], 0)
        assert result["scope1"]["total"] == 0.0
        assert result["scope2"]["location_based"] == 0.0
        assert result["scope3"]["total"] == 0.0
        assert result["total_location"] == 0.0
        assert result["total_market"] == 0.0

    def test_total_includes_all_scopes(self):
        result = build_summary(
            {"2026-01": {"gas_m3": 10}},
            {"2026-01": {"kwh": 100, "green": True}},
            [], [], 1.0,
        )
        s1 = result["scope1"]["total"]
        s2_loc = result["scope2"]["location_based"]
        s2_mkt = result["scope2"]["market_based"]
        s3 = result["scope3"]["total"]
        assert result["total_location"] == pytest.approx(s1 + s2_loc + s3)
        assert result["total_market"] == pytest.approx(s1 + s2_mkt + s3)
