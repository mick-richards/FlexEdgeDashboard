"""Tests for services/emissions.py — GHG Protocol calculations."""
from __future__ import annotations

import json

import pytest

from services.emissions import (
    FACTORS,
    build_summary,
    calc_scope1,
    calc_scope2,
    calc_scope3_cat3,
    calc_scope3_cat5,
    calc_scope3_cat7,
    calc_travel_emissions,
    load_commute,
    load_scope1,
    load_scope2,
    load_travel_log,
    save_commute,
    save_scope1,
    save_scope2,
    save_travel_log,
)


# ── Scope 1: Gas ──

class TestCalcScope1:
    def test_single_month(self):
        data = {"2026-01": {"gas_m3": 100}}
        result = calc_scope1(data)
        assert result == {"2026-01": 100 * FACTORS["gas_m3"]}

    def test_multiple_months(self):
        data = {
            "2026-01": {"gas_m3": 50},
            "2026-02": {"gas_m3": 75},
        }
        result = calc_scope1(data)
        assert len(result) == 2
        assert result["2026-01"] == pytest.approx(50 * 1.785)
        assert result["2026-02"] == pytest.approx(75 * 1.785)

    def test_zero_gas(self):
        result = calc_scope1({"2026-03": {"gas_m3": 0}})
        assert result["2026-03"] == 0.0

    def test_empty_data(self):
        assert calc_scope1({}) == {}

    def test_missing_gas_key_defaults_zero(self):
        result = calc_scope1({"2026-04": {}})
        assert result["2026-04"] == 0.0


# ── Scope 2: Electricity ──

class TestCalcScope2:
    def test_grey_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": False}}
        result = calc_scope2(data)
        expected = 1000 * FACTORS["electricity_kwh_location"]
        assert result["2026-01"]["location_based"] == pytest.approx(expected)
        assert result["2026-01"]["market_based"] == pytest.approx(expected)

    def test_green_electricity(self):
        data = {"2026-01": {"kwh": 1000, "green": True}}
        result = calc_scope2(data)
        assert result["2026-01"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["2026-01"]["market_based"] == 0.0

    def test_zero_kwh(self):
        result = calc_scope2({"2026-01": {"kwh": 0, "green": False}})
        assert result["2026-01"]["location_based"] == 0.0

    def test_missing_green_defaults_false(self):
        result = calc_scope2({"2026-01": {"kwh": 500}})
        # green defaults to False → market_based == location_based
        assert result["2026-01"]["market_based"] == result["2026-01"]["location_based"]


# ── Scope 3 ──

class TestScope3Categories:
    def test_cat3_wtt_uplift(self):
        s1, s2 = 100.0, 200.0
        result = calc_scope3_cat3(s1, s2)
        expected = 100 * 0.15 + 200 * 0.10  # 15 + 20 = 35
        assert result == pytest.approx(expected)

    def test_cat3_zero_inputs(self):
        assert calc_scope3_cat3(0, 0) == 0.0

    def test_cat5_waste(self):
        result = calc_scope3_cat5(fte_count=2.0)
        # 2 FTE × 15 kg/month × 0.5 factor × 12 months = 180
        assert result == pytest.approx(180.0)

    def test_cat5_zero_fte(self):
        assert calc_scope3_cat5(0) == 0.0

    def test_cat7_commuting_train(self):
        employees = [{
            "name": "Alice",
            "distance_km": 30,
            "days_per_week": 3,
            "mode": "Trein (NS)",
            "weeks_per_year": 46,
        }]
        result = calc_scope3_cat7(employees)
        # 30km × 2 (round trip) × 3 days × 46 weeks × 0.008
        expected = 30 * 2 * 3 * 46 * 0.008
        assert result == pytest.approx(expected)

    def test_cat7_defaults_46_weeks(self):
        employees = [{"distance_km": 10, "days_per_week": 5}]
        result = calc_scope3_cat7(employees)
        expected = 10 * 2 * 5 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)

    def test_cat7_multiple_employees(self):
        employees = [
            {"distance_km": 20, "days_per_week": 4, "mode": "Trein (NS)", "weeks_per_year": 46},
            {"distance_km": 15, "days_per_week": 5, "mode": "Auto (benzine)", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        e1 = 20 * 2 * 4 * 46 * 0.008
        e2 = 15 * 2 * 5 * 46 * 0.19
        assert result == pytest.approx(e1 + e2)

    def test_cat7_bike_zero_emissions(self):
        employees = [{"distance_km": 10, "days_per_week": 5, "mode": "Fiets"}]
        assert calc_scope3_cat7(employees) == 0.0

    def test_cat7_empty_list(self):
        assert calc_scope3_cat7([]) == 0.0


class TestTravelEmissions:
    def test_single_train_trip(self):
        trips = [{"distance_km": 100, "mode": "Trein"}]
        assert calc_travel_emissions(trips) == pytest.approx(100 * 0.008)

    def test_car_trip(self):
        trips = [{"distance_km": 50, "mode": "Auto (benzine)"}]
        assert calc_travel_emissions(trips) == pytest.approx(50 * 0.19)

    def test_short_flight(self):
        trips = [{"distance_km": 500, "mode": "Vlucht (<800 km)"}]
        assert calc_travel_emissions(trips) == pytest.approx(500 * 0.18)

    def test_multiple_trips(self):
        trips = [
            {"distance_km": 100, "mode": "Trein"},
            {"distance_km": 200, "mode": "Auto (elektrisch)"},
        ]
        expected = 100 * 0.008 + 200 * 0.05
        assert calc_travel_emissions(trips) == pytest.approx(expected)

    def test_zero_distance(self):
        trips = [{"distance_km": 0, "mode": "Trein"}]
        assert calc_travel_emissions(trips) == 0.0

    def test_empty_trips(self):
        assert calc_travel_emissions([]) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        trips = [{"distance_km": 100, "mode": "Onbekend"}]
        assert calc_travel_emissions(trips) == pytest.approx(100 * 0.008)


# ── Data persistence ──

class TestDataPersistence:
    def test_save_and_load_scope1(self, tmp_data_dir):
        data = {"2026-01": {"gas_m3": 42}}
        save_scope1(data)
        assert load_scope1() == data

    def test_save_and_load_scope2(self, tmp_data_dir):
        data = {"2026-01": {"kwh": 500, "green": True}}
        save_scope2(data)
        assert load_scope2() == data

    def test_save_and_load_commute(self, tmp_data_dir):
        employees = [{"name": "Bob", "distance_km": 25}]
        save_commute(employees)
        assert load_commute() == employees

    def test_save_and_load_travel_log(self, tmp_data_dir):
        trips = [{"date": "2026-01-15", "distance_km": 80, "mode": "Trein"}]
        save_travel_log(trips)
        assert load_travel_log() == trips

    def test_load_missing_file_returns_empty(self, tmp_data_dir):
        assert load_scope1() == {}
        assert load_scope2() == {}
        assert load_commute() == []
        assert load_travel_log() == []


# ── Build Summary ──

class TestBuildSummary:
    def test_basic_summary(self):
        s1_data = {"2026-01": {"gas_m3": 100}}
        s2_data = {"2026-01": {"kwh": 1000, "green": False}}
        commute = [{"distance_km": 20, "days_per_week": 5, "mode": "Trein (NS)", "weeks_per_year": 46}]
        trips = [{"distance_km": 200, "mode": "Trein"}]

        result = build_summary(s1_data, s2_data, commute, trips, fte_count=2.0)

        assert result["scope1"]["total"] == pytest.approx(100 * 1.785)
        assert result["scope2"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["scope3"]["cat5_waste"] == pytest.approx(180.0)
        assert result["scope3"]["cat6_business_travel"] == pytest.approx(200 * 0.008)
        assert result["scope3"]["total"] > 0
        assert result["total_location"] > 0

    def test_empty_summary(self):
        result = build_summary({}, {}, [], [], fte_count=0)
        assert result["scope1"]["total"] == 0.0
        assert result["scope2"]["location_based"] == 0.0
        assert result["scope3"]["total"] == 0.0
        assert result["total_location"] == 0.0

    def test_expense_scope3_integration(self):
        result = build_summary(
            {}, {}, [], [], fte_count=0,
            expense_scope3={"Cat 1 - Purchased Goods": 50.0, "Cat 2 - Capital": 30.0},
        )
        assert result["scope3"]["cat1_purchased_goods_services"] == pytest.approx(50.0)
        assert result["scope3"]["cat2_capital_goods"] == pytest.approx(30.0)

    def test_green_electricity_lowers_market_total(self):
        s2_grey = {"2026-01": {"kwh": 1000, "green": False}}
        s2_green = {"2026-01": {"kwh": 1000, "green": True}}

        grey = build_summary({}, s2_grey, [], [], 0)
        green = build_summary({}, s2_green, [], [], 0)

        assert green["total_market"] < grey["total_market"]
        # Location-based should be the same
        assert green["scope2"]["location_based"] == grey["scope2"]["location_based"]
