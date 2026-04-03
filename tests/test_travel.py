"""Tests for services/travel.py — calendar travel detection and route matching."""
from __future__ import annotations

import json

import pytest

from services.travel import (
    match_route,
    classify_event,
    scan_events,
    calc_trip_co2,
    load_known_routes,
    save_known_routes,
    CITY_SEPARATOR_RE,
)


# ── City separator regex ──


class TestCitySeparatorRegex:
    @pytest.mark.parametrize("subject,from_city,to_city", [
        ("Den Haag - Amsterdam", "Den Haag", "Amsterdam"),
        ("Leiden – Rotterdam", "Leiden", "Rotterdam"),
        ("Utrecht → Eindhoven", "Utrecht", "Eindhoven"),
        ("Breda > Tilburg", "Breda", "Tilburg"),
    ])
    def test_matches_city_patterns(self, subject, from_city, to_city):
        m = CITY_SEPARATOR_RE.match(subject.strip())
        assert m is not None
        assert m.group(1).strip() == from_city
        assert m.group(2).strip() == to_city

    def test_no_match_for_plain_text(self):
        assert CITY_SEPARATOR_RE.match("Team standup meeting") is None


# ── Route matching ──


class TestMatchRoute:
    ROUTES = [
        {"pattern": "den haag - amsterdam", "distance_km": 60, "mode": "Trein", "reverse": True},
        {"pattern": "leiden - rotterdam", "distance_km": 25, "mode": "Trein", "reverse": False},
    ]

    def test_exact_match(self):
        route = match_route("Den Haag - Amsterdam", self.ROUTES)
        assert route is not None
        assert route["distance_km"] == 60

    def test_reverse_match(self):
        route = match_route("Amsterdam - Den Haag", self.ROUTES)
        assert route is not None
        assert route["distance_km"] == 60

    def test_reverse_disabled(self):
        route = match_route("Rotterdam - Leiden", self.ROUTES)
        assert route is None

    def test_no_match(self):
        route = match_route("Groningen - Maastricht", self.ROUTES)
        assert route is None

    def test_case_insensitive(self):
        route = match_route("DEN HAAG - AMSTERDAM", self.ROUTES)
        assert route is not None

    def test_substring_match(self):
        route = match_route("Reis: Den Haag - Amsterdam (NS)", self.ROUTES)
        assert route is not None


# ── Event classification ──


class TestClassifyEvent:
    def test_online_meeting_skipped(self):
        event = {"subject": "Sprint review", "location": "Microsoft Teams", "onlineMeetingUrl": "https://teams.microsoft.com/123"}
        assert classify_event(event) is None

    def test_teams_keyword_in_location_skipped(self):
        event = {"subject": "1-on-1", "location": "teams", "categories": []}
        assert classify_event(event) is None

    def test_zoom_keyword_in_subject_skipped(self):
        event = {"subject": "Zoom call with client", "location": "", "categories": []}
        assert classify_event(event) is None

    def test_tagged_as_travel(self, tmp_data_dir):
        event = {
            "subject": "Klantbezoek",
            "location": "Kantoor Amsterdam",
            "categories": ["Reizen"],
            "start": "2026-04-01T09:00:00",
            "end": "2026-04-01T17:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["date"] == "2026-04-01"
        assert result["source"] == "Agenda"

    def test_city_pattern_detected(self, tmp_data_dir):
        event = {
            "subject": "Den Haag - Rotterdam",
            "location": "",
            "categories": [],
            "start": "2026-04-02T08:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result.get("from_city") == "Den Haag"
        assert result.get("to_city") == "Rotterdam"

    def test_travel_keyword_detected(self, tmp_data_dir):
        event = {
            "subject": "Trein naar Utrecht",
            "location": "",
            "categories": [],
            "start": "2026-04-03T07:00:00",
        }
        result = classify_event(event)
        assert result is not None

    def test_plain_meeting_not_detected(self):
        event = {
            "subject": "Weekelijkse sync",
            "location": "Vergaderzaal 2",
            "categories": [],
        }
        assert classify_event(event) is None

    def test_city_pattern_with_known_route(self, tmp_data_dir):
        # Write a known route to tmp_data_dir
        routes = {"routes": [{"pattern": "den haag - amsterdam", "distance_km": 60, "mode": "Trein", "reverse": True}]}
        (tmp_data_dir / "known_routes.json").write_text(json.dumps(routes), encoding="utf-8")

        event = {
            "subject": "Den Haag - Amsterdam",
            "location": "",
            "categories": [],
            "start": "2026-04-01T08:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["distance_km"] == 60
        assert result["matched_route"] is True
        assert result["needs_distance"] is False

    def test_unmatched_city_pattern_needs_distance(self, tmp_data_dir):
        event = {
            "subject": "Breda - Tilburg",
            "location": "",
            "categories": [],
            "start": "2026-04-01T08:00:00",
        }
        result = classify_event(event)
        assert result is not None
        assert result["distance_km"] == 0
        assert result["needs_distance"] is True


# ── Scan events ──


class TestScanEvents:
    def test_filters_travel_events(self, tmp_data_dir):
        events = [
            {"subject": "Team standup", "location": "Teams", "categories": []},
            {"subject": "Reis naar station", "location": "", "categories": [], "start": "2026-04-01T08:00:00"},
            {"subject": "Lunch", "location": "", "categories": []},
        ]
        results = scan_events(events)
        assert len(results) == 1
        assert "station" in results[0]["description"].lower()

    def test_empty_events(self, tmp_data_dir):
        assert scan_events([]) == []


# ── Trip CO₂ calculation ──


class TestCalcTripCO2:
    def test_train_trip(self):
        assert calc_trip_co2({"distance_km": 100, "mode": "Trein"}) == pytest.approx(100 * 0.008)

    def test_short_flight(self):
        assert calc_trip_co2({"distance_km": 500, "mode": "Vlucht (<800 km)"}) == pytest.approx(500 * 0.18)

    def test_zero_distance(self):
        assert calc_trip_co2({"distance_km": 0, "mode": "Trein"}) == 0.0

    def test_missing_distance(self):
        assert calc_trip_co2({"mode": "Trein"}) == 0.0


# ── Known routes persistence ──


class TestKnownRoutesPersistence:
    def test_save_and_load(self, tmp_data_dir):
        routes = [{"pattern": "a - b", "distance_km": 10, "mode": "Trein"}]
        save_known_routes(routes)
        loaded = load_known_routes()
        assert loaded == routes

    def test_load_missing_file(self, tmp_data_dir):
        assert load_known_routes() == []
