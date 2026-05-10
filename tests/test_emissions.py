"""Tests for services/emissions.py — GHG Protocol calculation engine."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from services.emissions import (
    FACTORS,
    COMMUTE_MODES,
    TRAVEL_MODES,
    calc_scope1,
    calc_scope2,
    calc_scope3_cat3,
    calc_scope3_cat5,
    calc_scope3_cat7,
    calc_travel_emissions,
    get_scope3_from_expenses,
    build_summary,
    _load_json,
    _save_json,
    load_scope1,
    save_scope1,
    load_commute,
    save_commute,
    load_travel_log,
    save_travel_log,
    load_holding_travel,
    DATA_DIR,
)


# ── Scope 1 ──

class TestCalcScope1:
    def test_single_month(self):
        data = {"202501": {"gas_m3": 100}}
        result = calc_scope1(data)
        assert result == {"202501": 100 * FACTORS["gas_m3"]}

    def test_multiple_months(self):
        data = {
            "202501": {"gas_m3": 100},
            "202502": {"gas_m3": 50},
        }
        result = calc_scope1(data)
        assert result["202501"] == pytest.approx(178.5)
        assert result["202502"] == pytest.approx(89.25)

    def test_zero_gas(self):
        result = calc_scope1({"202501": {"gas_m3": 0}})
        assert result["202501"] == 0.0

    def test_missing_gas_key(self):
        result = calc_scope1({"202501": {}})
        assert result["202501"] == 0.0

    def test_empty_data(self):
        assert calc_scope1({}) == {}


# ── Scope 2 ──

class TestCalcScope2:
    def test_grey_electricity(self):
        data = {"202501": {"kwh": 1000, "green": False}}
        result = calc_scope2(data)
        expected = 1000 * FACTORS["electricity_kwh_location"]
        assert result["202501"]["location_based"] == pytest.approx(expected)
        assert result["202501"]["market_based"] == pytest.approx(expected)

    def test_green_electricity(self):
        data = {"202501": {"kwh": 1000, "green": True}}
        result = calc_scope2(data)
        assert result["202501"]["location_based"] == pytest.approx(328.0)
        assert result["202501"]["market_based"] == pytest.approx(0.0)

    def test_default_not_green(self):
        data = {"202501": {"kwh": 500}}
        result = calc_scope2(data)
        # green defaults to False
        assert result["202501"]["market_based"] == result["202501"]["location_based"]

    def test_empty_data(self):
        assert calc_scope2({}) == {}


# ── Scope 3 Category 3: WTT uplift ──

class TestCalcScope3Cat3:
    def test_basic_uplift(self):
        result = calc_scope3_cat3(1000.0, 500.0)
        expected = 1000.0 * 0.15 + 500.0 * 0.10
        assert result == pytest.approx(expected)

    def test_zero_inputs(self):
        assert calc_scope3_cat3(0, 0) == 0.0


# ── Scope 3 Category 5: Waste ──

class TestCalcScope3Cat5:
    def test_two_fte(self):
        result = calc_scope3_cat5(2.0)
        expected = 2.0 * 15.0 * 0.5 * 12
        assert result == pytest.approx(expected)

    def test_zero_fte(self):
        assert calc_scope3_cat5(0) == 0.0

    def test_fractional_fte(self):
        result = calc_scope3_cat5(1.5)
        assert result == pytest.approx(1.5 * 15.0 * 0.5 * 12)


# ── Scope 3 Category 7: Commuting ──

class TestCalcScope3Cat7:
    def test_single_employee_train(self):
        employees = [{
            "name": "Alice",
            "distance_km": 20,
            "days_per_week": 3,
            "mode": "Trein (NS)",
            "weeks_per_year": 46,
        }]
        result = calc_scope3_cat7(employees)
        expected = 20 * 2 * 3 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)

    def test_default_weeks(self):
        employees = [{"distance_km": 10, "days_per_week": 5, "mode": "Trein (NS)"}]
        result = calc_scope3_cat7(employees)
        expected = 10 * 2 * 5 * 46 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)

    def test_bicycle_zero_emissions(self):
        employees = [{"distance_km": 15, "days_per_week": 5, "mode": "Fiets", "weeks_per_year": 46}]
        assert calc_scope3_cat7(employees) == 0.0

    def test_multiple_employees(self):
        employees = [
            {"distance_km": 20, "days_per_week": 3, "mode": "Trein (NS)", "weeks_per_year": 46},
            {"distance_km": 30, "days_per_week": 4, "mode": "Auto (benzine)", "weeks_per_year": 46},
        ]
        result = calc_scope3_cat7(employees)
        train_co2 = 20 * 2 * 3 * 46 * FACTORS["commute_train"]
        car_co2 = 30 * 2 * 4 * 46 * FACTORS["commute_car_petrol"]
        assert result == pytest.approx(train_co2 + car_co2)

    def test_empty_employees(self):
        assert calc_scope3_cat7([]) == 0.0

    def test_unknown_mode_falls_back_to_train(self):
        employees = [{"distance_km": 10, "days_per_week": 1, "mode": "Onbekend", "weeks_per_year": 1}]
        result = calc_scope3_cat7(employees)
        expected = 10 * 2 * 1 * 1 * FACTORS["commute_train"]
        assert result == pytest.approx(expected)


# ── Scope 3 Category 6: Business Travel ──

class TestCalcTravelEmissions:
    def test_single_trip_train(self):
        trips = [{"distance_km": 100, "mode": "Trein"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(100 * FACTORS["travel_train"])

    def test_flight_short(self):
        trips = [{"distance_km": 500, "mode": "Vlucht (<800 km)"}]
        result = calc_travel_emissions(trips)
        assert result == pytest.approx(500 * FACTORS["travel_flight_short"])

    def test_multiple_trips(self):
        trips = [
            {"distance_km": 100, "mode": "Trein"},
            {"distance_km": 50, "mode": "Auto (benzine)"},
        ]
        result = calc_travel_emissions(trips)
        expected = 100 * FACTORS["travel_train"] + 50 * FACTORS["travel_car_petrol"]
        assert result == pytest.approx(expected)

    def test_empty_trips(self):
        assert calc_travel_emissions([]) == 0.0

    def test_missing_distance(self):
        trips = [{"mode": "Trein"}]
        assert calc_travel_emissions(trips) == 0.0


# ── Expense-based Scope 3 ──

class TestGetScope3FromExpenses:
    def test_with_dataframe(self):
        import pandas as pd
        df = pd.DataFrame({
            "scope3_cat": ["Cat 1: Purchased Services", "Cat 1: Purchased Services", "Cat 2: Capital Goods"],
            "co2e_kg": [10.0, 5.0, 20.0],
        })
        result = get_scope3_from_expenses(df)
        assert result["Cat 1: Purchased Services"] == pytest.approx(15.0)
        assert result["Cat 2: Capital Goods"] == pytest.approx(20.0)

    def test_empty_dataframe(self):
        import pandas as pd
        assert get_scope3_from_expenses(pd.DataFrame()) == {}

    def test_none_input(self):
        assert get_scope3_from_expenses(None) == {}


# ── Build Summary (integration) ──

class TestBuildSummary:
    def test_full_summary(self):
        scope1 = {"202501": {"gas_m3": 100}}
        scope2 = {"202501": {"kwh": 1000, "green": False}}
        commute = [{"distance_km": 20, "days_per_week": 3, "mode": "Trein (NS)", "weeks_per_year": 46}]
        travel = [{"distance_km": 100, "mode": "Trein"}]
        fte = 2.0

        result = build_summary(scope1, scope2, commute, travel, fte)

        assert result["scope1"]["total"] == pytest.approx(100 * 1.785)
        assert result["scope2"]["location_based"] == pytest.approx(1000 * 0.328)
        assert result["scope3"]["cat5_waste"] == pytest.approx(2.0 * 15 * 0.5 * 12)
        assert result["scope3"]["cat6_business_travel"] == pytest.approx(100 * 0.008)
        assert "total_location" in result
        assert "total_market" in result

    def test_empty_data(self):
        result = build_summary({}, {}, [], [], 0)
        assert result["scope1"]["total"] == 0.0
        assert result["scope2"]["location_based"] == 0.0
        assert result["scope3"]["total"] == 0.0
        assert result["total_location"] == 0.0

    def test_with_expense_scope3(self):
        expense = {"Cat 1: Purchased Services": 50.0, "Cat 8: Leased assets": 10.0}
        result = build_summary({}, {}, [], [], 0, expense_scope3=expense)
        assert result["scope3"]["cat1_purchased_goods_services"] == pytest.approx(50.0)
        assert result["scope3"]["cat8_leased_assets"] == pytest.approx(10.0)

    def test_total_includes_all_scopes(self):
        scope1 = {"202501": {"gas_m3": 10}}
        scope2 = {"202501": {"kwh": 100, "green": False}}
        result = build_summary(scope1, scope2, [], [], 1.0)
        s1 = result["scope1"]["total"]
        s2 = result["scope2"]["location_based"]
        s3 = result["scope3"]["total"]
        assert result["total_location"] == pytest.approx(s1 + s2 + s3)


# ── Data persistence ──

class TestPersistence:
    def test_save_and_load_json(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        _save_json("test.json", {"key": "value"})
        assert _load_json("test.json") == {"key": "value"}

    def test_load_nonexistent(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        assert _load_json("nope.json") == {}

    def test_scope1_roundtrip(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        data = {"202501": {"gas_m3": 42}}
        save_scope1(data)
        assert load_scope1() == data

    def test_commute_roundtrip(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        employees = [{"name": "Test", "distance_km": 10}]
        save_commute(employees)
        assert load_commute() == employees

    def test_travel_log_roundtrip(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        trips = [{"date": "2026-01-15", "distance_km": 100, "mode": "Trein"}]
        save_travel_log(trips)
        assert load_travel_log() == trips

    def test_load_holding_travel(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.emissions.DATA_DIR", tmp_data_dir)
        holding_data = {
            "transactions": [
                {"zakelijk_flexedge": True, "distance_km": 50, "date": "2026-01-10",
                 "description": "Trip A", "mode": "Trein"},
                {"zakelijk_flexedge": False, "distance_km": 100},  # not business
                {"zakelijk_flexedge": True, "distance_km": 0},     # zero distance
            ]
        }
        (tmp_data_dir / "holding_mick.json").write_text(
            json.dumps(holding_data), encoding="utf-8"
        )
        trips = load_holding_travel()
        assert len(trips) == 1
        assert trips[0]["distance_km"] == 50
        assert trips[0]["source"] == "Holding (Mick)"


# ── Factor sanity checks ──

class TestFactors:
    def test_all_commute_modes_have_factors(self):
        for label, key in COMMUTE_MODES.items():
            assert key in FACTORS, f"Missing factor for commute mode {label}"

    def test_all_travel_modes_have_factors(self):
        for label, key in TRAVEL_MODES.items():
            assert key in FACTORS, f"Missing factor for travel mode {label}"

    def test_bike_is_zero(self):
        assert FACTORS["commute_bike"] == 0.0

    def test_green_electricity_is_zero(self):
        assert FACTORS["electricity_kwh_market_green"] == 0.0
