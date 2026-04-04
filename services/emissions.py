"""Emissions calculation service for GHG Protocol reporting.

Calculates Scope 1, 2, and 3 emissions for FlexEdge BV.
Emission factors sourced from co2emissiefactoren.nl, EXIOBASE, and DEFRA.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent.parent / "data"

# ── Emission factors ──
# Sources: co2emissiefactoren.nl (2024), EXIOBASE v3.8.2, DEFRA 2024

FACTORS = {
    # Scope 1
    "gas_m3": 1.785,          # kg CO₂e per m³ natural gas (co2emissiefactoren.nl 2024)

    # Scope 2
    "electricity_kwh_location": 0.328,  # kg CO₂e per kWh — NL grid location-based (CBS/RVO 2024)
    "electricity_kwh_market_green": 0.0,  # kg CO₂e per kWh — green certified (GoO)
    "heat_gj": 25.7,          # kg CO₂e per GJ — district heating NL average

    # Scope 3 Cat 3: WTT (well-to-tank) uplift factors
    "wtt_gas_factor": 0.15,   # 15% uplift on Scope 1 gas
    "wtt_elec_factor": 0.10,  # 10% uplift on Scope 2 electricity

    # Scope 3 Cat 5: Waste
    "waste_kg_per_fte_month": 15.0,  # kg waste per FTE per month (office average)
    "waste_emission_factor": 0.5,     # kg CO₂e per kg mixed office waste

    # Scope 3 Cat 7: Commuting — per km, one way
    "commute_train": 0.008,   # kg CO₂e per km — NS electric train (co2emissiefactoren.nl)
    "commute_bus": 0.030,     # kg CO₂e per km — bus
    "commute_car_petrol": 0.19,  # kg CO₂e per km — average petrol car
    "commute_car_electric": 0.05,  # kg CO₂e per km — electric car (NL grid)
    "commute_ebike": 0.005,   # kg CO₂e per km — e-bike
    "commute_bike": 0.0,      # kg CO₂e per km — bicycle

    # Scope 3 Cat 6: Business travel — per km
    "travel_train": 0.008,
    "travel_car_petrol": 0.19,
    "travel_car_electric": 0.05,
    "travel_flight_short": 0.18,  # <800 km
    "travel_flight_long": 0.11,   # >800 km
}

COMMUTE_MODES = {
    "Trein (NS)": "commute_train",
    "Bus/tram/metro": "commute_bus",
    "Auto (benzine)": "commute_car_petrol",
    "Auto (elektrisch)": "commute_car_electric",
    "E-bike": "commute_ebike",
    "Fiets": "commute_bike",
}

TRAVEL_MODES = {
    "Trein": "travel_train",
    "Auto (benzine)": "travel_car_petrol",
    "Auto (elektrisch)": "travel_car_electric",
    "Vlucht (<800 km)": "travel_flight_short",
    "Vlucht (>800 km)": "travel_flight_long",
}


# ── Data persistence ──

def _load_json(filename: str) -> dict:
    path = DATA_DIR / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _save_json(filename: str, data: dict) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def load_scope1() -> dict:
    return _load_json("emissions_scope1.json")


def save_scope1(data: dict) -> None:
    _save_json("emissions_scope1.json", data)


def load_scope2() -> dict:
    return _load_json("emissions_scope2.json")


def save_scope2(data: dict) -> None:
    _save_json("emissions_scope2.json", data)


def load_commute() -> list[dict]:
    data = _load_json("emissions_commute.json")
    return data.get("employees", [])


def save_commute(employees: list[dict]) -> None:
    _save_json("emissions_commute.json", {"employees": employees})


def load_travel_log() -> list[dict]:
    data = _load_json("travel_log.json")
    return data.get("trips", [])


def load_holding_travel() -> list[dict]:
    """Load zakelijke reizen from all holding files and merge into travel format."""
    trips = []
    for path in DATA_DIR.glob("holding_*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for tx in data.get("transactions", []):
            if tx.get("zakelijk_flexedge") and tx.get("distance_km", 0) > 0:
                trips.append({
                    "date": tx.get("date", ""),
                    "description": tx.get("description", ""),
                    "distance_km": tx.get("distance_km", 0),
                    "mode": tx.get("mode", "Trein"),
                    "source": f"Holding ({path.stem.replace('holding_', '').capitalize()})",
                })
    return trips


def save_travel_log(trips: list[dict]) -> None:
    _save_json("travel_log.json", {"trips": trips})


# ── Calculations ──

def calc_scope1(data: dict) -> dict[str, float]:
    """Calculate Scope 1 emissions from gas consumption per month."""
    results = {}
    for month_key, values in data.items():
        gas_m3 = values.get("gas_m3", 0)
        results[month_key] = gas_m3 * FACTORS["gas_m3"]
    return results


def calc_scope2(data: dict) -> dict[str, dict[str, float]]:
    """Calculate Scope 2 emissions (location-based and market-based) per month."""
    results = {}
    for month_key, values in data.items():
        kwh = values.get("kwh", 0)
        green = values.get("green", False)
        location_based = kwh * FACTORS["electricity_kwh_location"]
        market_based = kwh * FACTORS["electricity_kwh_market_green"] if green else location_based
        results[month_key] = {
            "location_based": location_based,
            "market_based": market_based,
        }
    return results


def calc_scope3_cat3(scope1_total: float, scope2_total: float) -> float:
    """Cat 3: Fuel & energy related activities (WTT uplift)."""
    return scope1_total * FACTORS["wtt_gas_factor"] + scope2_total * FACTORS["wtt_elec_factor"]


def calc_scope3_cat5(fte_count: float) -> float:
    """Cat 5: Waste generated in operations (forfaitaire schatting per jaar)."""
    return fte_count * FACTORS["waste_kg_per_fte_month"] * FACTORS["waste_emission_factor"] * 12


def calc_scope3_cat7(employees: list[dict], year: int | None = None) -> float:
    """Cat 7: Employee commuting — annual total.

    Each employee dict: {name, distance_km, days_per_week, mode, weeks_per_year}
    """
    total = 0.0
    for emp in employees:
        distance = emp.get("distance_km", 0)
        days = emp.get("days_per_week", 0)
        weeks = emp.get("weeks_per_year", 46)  # default: 46 werkweken
        mode_key = COMMUTE_MODES.get(emp.get("mode", "Trein (NS)"), "commute_train")
        factor = FACTORS[mode_key]
        # Round trip
        total += distance * 2 * days * weeks * factor
    return total


def calc_travel_emissions(trips: list[dict]) -> float:
    """Cat 6: Business travel from travel log."""
    total = 0.0
    for trip in trips:
        km = trip.get("distance_km", 0)
        mode_key = TRAVEL_MODES.get(trip.get("mode", "Trein"), "travel_train")
        factor = FACTORS[mode_key]
        total += km * factor
    return total


def build_summary(
    scope1_data: dict,
    scope2_data: dict,
    commute_employees: list[dict],
    travel_trips: list[dict],
    fte_count: float,
    expense_scope3: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Build complete GHG summary across all scopes."""
    # Scope 1
    s1_monthly = calc_scope1(scope1_data)
    s1_total = sum(s1_monthly.values())

    # Scope 2
    s2_monthly = calc_scope2(scope2_data)
    s2_location = sum(m["location_based"] for m in s2_monthly.values())
    s2_market = sum(m["market_based"] for m in s2_monthly.values())

    # Scope 3
    s3_cat3 = calc_scope3_cat3(s1_total, s2_location)
    s3_cat5 = calc_scope3_cat5(fte_count)
    s3_cat6 = calc_travel_emissions(travel_trips)
    s3_cat7 = calc_scope3_cat7(commute_employees)

    # From expense categorization
    expense_scope3 = expense_scope3 or {}
    s3_cat1 = sum(v for k, v in expense_scope3.items() if "Cat 1" in k)
    s3_cat2 = sum(v for k, v in expense_scope3.items() if "Cat 2" in k)
    s3_cat8 = sum(v for k, v in expense_scope3.items() if "Cat 8" in k)

    s3_total = s3_cat1 + s3_cat2 + s3_cat3 + s3_cat5 + s3_cat6 + s3_cat7 + s3_cat8

    return {
        "scope1": {"total": s1_total, "monthly": s1_monthly},
        "scope2": {
            "location_based": s2_location,
            "market_based": s2_market,
            "monthly": s2_monthly,
        },
        "scope3": {
            "total": s3_total,
            "cat1_purchased_goods_services": s3_cat1,
            "cat2_capital_goods": s3_cat2,
            "cat3_fuel_energy_wtt": s3_cat3,
            "cat5_waste": s3_cat5,
            "cat6_business_travel": s3_cat6,
            "cat7_commuting": s3_cat7,
            "cat8_leased_assets": s3_cat8,
        },
        "total_location": s1_total + s2_location + s3_total,
        "total_market": s1_total + s2_market + s3_total,
    }
