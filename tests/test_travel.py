"""Tests for services/travel.py — travel detection and classification."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from services.travel import (
    match_route,
    classify_event,
    scan_events,
    calc_trip_co2,
    CITY_SEPARATOR_RE,
    TRAVEL_KEYWORDS,
    ONLINE_KEYWORDS,
    load_known_routes,
    save_known_routes,
)
from services.emissions import FACTORS


# ── City separator regex ──

class TestCitySeparatorRegex:
    @pytest.mark.parametrize("subject,expected_from,expected_to", [
        ("Den Haag - Rotterdam", "Den Haag", "Rotterdam"),
        ("Amsterdam – Utrecht", "Amsterdam", "Utrecht"),
        ("Leiden → Delft", "Leiden", "Delft"),
        ("Breda > Tilburg", "Breda", "Tilburg"),
    ])
    def test_matches_separators(self, subject, expected_from, expected_to):
        m = CITY_SEPARATOR_RE.match(subject)
        assert m is not None
        assert m.group(1).strip() == expected_from
        assert m.group(2).strip() == expected_to

    def test_no_separator(self):
        assert CITY_SEPARATOR_RE.match("Team standup") is None


# ── Route matching ──

class TestMatchRoute:
    def test_exact_match(self):
        routes = [{"pattern": "Den Haag - Rotterdam", "distance_km": 25, "mode": "Trein"}]
        result = match_route("Den Haag - Rotterdam", routes)
        assert result is not None
        assert result["distance_km"] == 25

    def test_case_insensitive(self):
        routes = [{"pattern": "den haag - rotterdam", "distance_km": 25, "mode": "Trein"}]
        result = match_route("Den Haag - Rotterdam", routes)
        assert result is not None

    def test_substring_match(self):
        routes = [{"pattern": "schiphol", "distance_km": 40, "mode": "Trein"}]
        result = match_route("Reis naar Schiphol Airport", routes)
        assert result is not None

    def test_reverse_match(self):
        routes = [{"pattern": "den haag - rotterdam", "distance_km": 25, "mode": "Trein", "reverse": True}]
        result = match_route("Rotterdam - Den Haag", routes)
        assert result is not None

    def test_no_reverse_when_disabled(self):
        routes = [{"pattern": "den haag - rotterdam", "distance_km": 25, "mode": "Trein", "reverse": False}]
        result = match_route("Rotterdam - Den Haag", routes)
        assert result is None

    def test_no_match(self):
        routes = [{"pattern": "den haag - rotterdam", "distance_km": 25, "mode": "Trein"}]
        result = match_route("Team standup", routes)
        assert result is None

    def test_empty_routes(self):
        assert match_route("anything", []) is None


# ── Event classification ──

class TestClassifyEvent:
    @patch("services.travel.load_known_routes", return_value=[])
    def test_city_to_city_detected(self, _):
        event = {"subject": "Den Haag - Rotterdam", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is not None
        assert result["from_city"] == "Den Haag"
        assert result["to_city"] == "Rotterdam"
        assert result["needs_distance"] is True

    @patch("services.travel.load_known_routes", return_value=[])
    def test_travel_keyword_detected(self, _):
        event = {"subject": "Trein naar klant", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_travel_category_detected(self, _):
        event = {"subject": "Klantbezoek", "categories": ["Reizen"], "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_online_meeting_excluded(self, _):
        event = {"subject": "Teams standup", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_meeting_url_excluded(self, _):
        event = {"subject": "Den Haag - Rotterdam", "onlineMeetingUrl": "https://teams.live/abc",
                 "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_regular_meeting_not_detected(self, _):
        event = {"subject": "Sprint planning", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is None

    @patch("services.travel.load_known_routes", return_value=[
        {"pattern": "den haag - rotterdam", "distance_km": 25, "mode": "Trein"}
    ])
    def test_matched_route_fills_distance(self, _):
        event = {"subject": "Den Haag - Rotterdam", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        assert result is not None
        assert result["distance_km"] == 25
        assert result["matched_route"] is True
        assert result["needs_distance"] is False

    @patch("services.travel.load_known_routes", return_value=[])
    def test_long_city_name_rejected(self, _):
        long_name = "A" * 35
        event = {"subject": f"{long_name} - Rotterdam", "start": "2026-01-15T09:00:00"}
        result = classify_event(event)
        # Long "city" name (35 chars) > 30 char limit, so city_pattern is False
        # No travel keyword or tag either
        assert result is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_date_extracted_from_start(self, _):
        event = {"subject": "Trein naar klant", "start": "2026-03-20T14:30:00"}
        result = classify_event(event)
        assert result["date"] == "2026-03-20"


# ── Scan events ──

class TestScanEvents:
    @patch("services.travel.load_known_routes", return_value=[])
    def test_filters_travel_events(self, _):
        events = [
            {"subject": "Den Haag - Rotterdam", "start": "2026-01-15T09:00:00"},
            {"subject": "Sprint planning", "start": "2026-01-15T10:00:00"},
            {"subject": "Station Amsterdam", "start": "2026-01-16T08:00:00"},
        ]
        result = scan_events(events)
        assert len(result) == 2

    @patch("services.travel.load_known_routes", return_value=[])
    def test_empty_events(self, _):
        assert scan_events([]) == []


# ── CO2 calculation ──

class TestCalcTripCo2:
    def test_train_trip(self):
        trip = {"distance_km": 100, "mode": "Trein"}
        assert calc_trip_co2(trip) == pytest.approx(100 * FACTORS["travel_train"])

    def test_car_trip(self):
        trip = {"distance_km": 50, "mode": "Auto (benzine)"}
        assert calc_trip_co2(trip) == pytest.approx(50 * FACTORS["travel_car_petrol"])

    def test_zero_distance(self):
        assert calc_trip_co2({"distance_km": 0, "mode": "Trein"}) == 0.0

    def test_missing_distance(self):
        assert calc_trip_co2({"mode": "Trein"}) == 0.0

    def test_unknown_mode_defaults_to_train(self):
        trip = {"distance_km": 100, "mode": "Onbekend"}
        assert calc_trip_co2(trip) == pytest.approx(100 * FACTORS["travel_train"])


# ── Route persistence ──

class TestRoutePersistence:
    def test_save_and_load(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.travel.DATA_DIR", tmp_data_dir)
        routes = [{"pattern": "test", "distance_km": 10, "mode": "Trein"}]
        save_known_routes(routes)
        loaded = load_known_routes()
        assert loaded == routes

    def test_load_nonexistent(self, tmp_data_dir, monkeypatch):
        monkeypatch.setattr("services.travel.DATA_DIR", tmp_data_dir)
        assert load_known_routes() == []
