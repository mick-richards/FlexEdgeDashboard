"""Tests for services/travel.py — travel detection and route matching."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from services.travel import (
    CITY_SEPARATOR_RE,
    ONLINE_KEYWORDS,
    TRAVEL_KEYWORDS,
    calc_trip_co2,
    classify_event,
    match_route,
    scan_events,
)


# ── Regex patterns ──

class TestCitySeparatorRegex:
    @pytest.mark.parametrize("subject,from_city,to_city", [
        ("Leiden - Den Haag", "Leiden", "Den Haag"),
        ("Amsterdam – Rotterdam", "Amsterdam", "Rotterdam"),
        ("Utrecht → Eindhoven", "Utrecht", "Eindhoven"),
        ("Breda > Tilburg", "Breda", "Tilburg"),
    ])
    def test_matches_city_patterns(self, subject, from_city, to_city):
        m = CITY_SEPARATOR_RE.match(subject)
        assert m is not None
        assert m.group(1).strip() == from_city
        assert m.group(2).strip() == to_city

    def test_no_match_for_plain_text(self):
        assert CITY_SEPARATOR_RE.match("Team standup meeting") is None


# ── Route matching ──

class TestMatchRoute:
    @pytest.fixture
    def routes(self):
        return [
            {"pattern": "Leiden - Den Haag", "distance_km": 20, "mode": "Trein", "reverse": True},
            {"pattern": "Amsterdam - Utrecht", "distance_km": 40, "mode": "Trein", "reverse": False},
        ]

    def test_exact_match(self, routes):
        result = match_route("Leiden - Den Haag", routes)
        assert result is not None
        assert result["distance_km"] == 20

    def test_case_insensitive(self, routes):
        result = match_route("leiden - den haag", routes)
        assert result is not None

    def test_reverse_match(self, routes):
        result = match_route("Den Haag - Leiden", routes)
        assert result is not None
        assert result["distance_km"] == 20

    def test_reverse_disabled(self, routes):
        result = match_route("Utrecht - Amsterdam", routes)
        assert result is None

    def test_no_match(self, routes):
        result = match_route("Groningen - Leeuwarden", routes)
        assert result is None

    def test_partial_match_in_longer_subject(self, routes):
        result = match_route("Reis: Leiden - Den Haag overleg", routes)
        assert result is not None

    def test_empty_routes(self):
        assert match_route("Leiden - Den Haag", []) is None


# ── Event classification ──

class TestClassifyEvent:
    def _make_event(self, **overrides):
        base = {
            "subject": "",
            "start": "2026-04-23T09:00:00",
            "end": "2026-04-23T10:00:00",
            "location": "",
            "categories": [],
            "onlineMeetingUrl": "",
        }
        base.update(overrides)
        return base

    @patch("services.travel.load_known_routes", return_value=[])
    def test_city_pattern_detected(self, mock_routes):
        event = self._make_event(subject="Leiden - Den Haag")
        result = classify_event(event)
        assert result is not None
        assert result["from_city"] == "Leiden"
        assert result["to_city"] == "Den Haag"
        assert result["needs_distance"] is True

    @patch("services.travel.load_known_routes", return_value=[])
    def test_travel_keyword_detected(self, mock_routes):
        event = self._make_event(subject="Trein naar klant")
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_tagged_category_detected(self, mock_routes):
        event = self._make_event(subject="Klantbezoek", categories=["Reizen"])
        result = classify_event(event)
        assert result is not None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_online_meeting_skipped(self, mock_routes):
        event = self._make_event(
            subject="Leiden - Den Haag",
            onlineMeetingUrl="https://teams.microsoft.com/meet/123",
        )
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_teams_keyword_in_location_skipped(self, mock_routes):
        event = self._make_event(
            subject="Trein naar Amsterdam",
            location="Microsoft Teams Meeting",
        )
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[])
    def test_plain_meeting_not_detected(self, mock_routes):
        event = self._make_event(subject="Weekly standup")
        assert classify_event(event) is None

    @patch("services.travel.load_known_routes", return_value=[
        {"pattern": "Leiden - Den Haag", "distance_km": 20, "mode": "Trein", "reverse": True},
    ])
    def test_known_route_fills_distance(self, mock_routes):
        event = self._make_event(subject="Leiden - Den Haag")
        result = classify_event(event)
        assert result is not None
        assert result["distance_km"] == 20
        assert result["mode"] == "Trein"
        assert result["matched_route"] is True
        assert result["needs_distance"] is False

    @patch("services.travel.load_known_routes", return_value=[])
    def test_date_extracted(self, mock_routes):
        event = self._make_event(subject="Reizen", start="2026-05-01T08:30:00")
        result = classify_event(event)
        assert result["date"] == "2026-05-01"

    @patch("services.travel.load_known_routes", return_value=[])
    def test_long_subject_not_city_pattern(self, mock_routes):
        """Subjects with >30 char parts are not treated as city-to-city."""
        event = self._make_event(
            subject="Very long description of something - Another very long description of something else",
            categories=["Reizen"],  # still detected via tag
        )
        result = classify_event(event)
        assert result is not None
        assert "from_city" not in result


# ── Scan events ──

class TestScanEvents:
    @patch("services.travel.load_known_routes", return_value=[])
    def test_filters_non_travel(self, mock_routes):
        events = [
            {"subject": "Leiden - Den Haag", "start": "2026-04-23T09:00:00",
             "end": "2026-04-23T10:00:00", "location": "", "categories": [],
             "onlineMeetingUrl": ""},
            {"subject": "Standup", "start": "2026-04-23T09:30:00",
             "end": "2026-04-23T09:45:00", "location": "", "categories": [],
             "onlineMeetingUrl": ""},
        ]
        results = scan_events(events)
        assert len(results) == 1
        assert results[0]["description"] == "Leiden - Den Haag"


# ── CO₂ calculation ──

class TestCalcTripCo2:
    def test_train_trip(self):
        assert calc_trip_co2({"distance_km": 100, "mode": "Trein"}) == pytest.approx(0.8)

    def test_car_trip(self):
        assert calc_trip_co2({"distance_km": 50, "mode": "Auto (benzine)"}) == pytest.approx(9.5)

    def test_zero_distance(self):
        assert calc_trip_co2({"distance_km": 0, "mode": "Trein"}) == 0.0

    def test_unknown_mode_defaults(self):
        result = calc_trip_co2({"distance_km": 100, "mode": "Paard"})
        assert result == pytest.approx(100 * 0.008)


# ── Known routes persistence ──

class TestKnownRoutesPersistence:
    def test_save_and_load(self, tmp_data_dir):
        from services.travel import load_known_routes, save_known_routes

        routes = [{"pattern": "A - B", "distance_km": 10, "mode": "Trein"}]
        save_known_routes(routes)
        assert load_known_routes() == routes

    def test_load_missing_returns_empty(self, tmp_data_dir):
        from services.travel import load_known_routes
        assert load_known_routes() == []
